#!/usr/bin/env python3
"""
Numerical checks for the selected AC-link DAB design.

 A. Switched-waveform simulation of one cell over a full line cycle
    (ideal square-wave bridges, series inductance only) - compares transferred
    power and transformer rms current against the closed-form expressions used
    in dab_design.py.

 B. Sample-by-sample closed-loop simulation of unannounced power reversal with
    the "virtual transformer" control law (load-current feed-forward + PI on
    the port voltage difference, one-sample computation delay).

Run:  python3 dab_sim.py
"""
import math
import os

import numpy as np

import dab_design as dd

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "img")
F_SW = 70e3
N_CELLS = 2
L_CELL = dd.l_cell_required(F_SW, N_CELLS)


# ---------------------------------------------------------------- part A ---
def switched_check(v_rms, p_total, n_active, plot_ax=None):
    o = dd.op_point(v_rms, p_total, n_active, F_SW, L_CELL)
    d = o["d"]
    spp = 16000                                  # samples per switching period
    n_per = int(round(F_SW / dd.F_LINE / 4))     # quarter line cycle (symmetry)
    t = (np.arange(n_per * spp) + 0.5) / (spp * F_SW)
    env = o["vpk"] * np.abs(np.sin(2 * math.pi * dd.F_LINE * t))
    ph = (t * F_SW) % 1.0
    s1 = np.where(ph < 0.5, 1.0, -1.0)
    s2 = np.where(((ph - d / 2) % 1.0) < 0.5, 1.0, -1.0)
    v_l = env * (s1 - s2)
    i = np.cumsum(v_l) / (spp * F_SW) / L_CELL
    # remove the integration constant period by period (steady state, no dc)
    i = i - np.repeat(i.reshape(n_per, spp).mean(axis=1), spp)
    p_sim = float(np.mean(env * s1 * i)) * n_active
    i_rms = float(np.sqrt(np.mean(i ** 2)))
    if plot_ax is not None:
        k = n_per - 3                            # periods at the line crest
        sl = slice(k * spp, (k + 2) * spp)
        tt = (t[sl] - t[k * spp]) * 1e6
        plot_ax.plot(tt, env[sl] * s1[sl], lw=0.9, label="v primary bridge, V")
        plot_ax.plot(tt, env[sl] * s2[sl], lw=0.9, label="v secondary bridge, V")
        plot_ax.plot(tt, i[sl], lw=1.4, label="transformer current, A")
        plot_ax.set_title(f"{p_total/1e3:.0f} kW at {v_rms:.0f} V, {n_active} cell(s), line crest")
        plot_ax.set_xlabel("time, us")
        plot_ax.grid(alpha=0.3)
        plot_ax.legend(fontsize=7, loc="lower right")
    return dict(v=v_rms, p_set=p_total, p_sim=p_sim, i_rms_sim=i_rms, i_rms_model=o["i_tr"], d=d)


# ---------------------------------------------------------------- part B ---
def phasor_for_power(v_rms, p, z):
    """Port-2 EMF phasor (rms) that makes real power p flow 1 -> 2 through impedance z."""
    return v_rms - (p / v_rms) * z


def reversal(v_rms, p_before, p_after, n_active, c_link=40e-6, l_f=30e-6, r_f=10e-3, r_d=1.0,
             kp=0.6, i_lim=None, e2_scale_after=None, plot_ax=None, label=""):
    """
    Both ports are EMFs behind a damped filter inductance (l_f + r_f, with r_d
    in parallel).  The link capacitors sit on the DC side of the unfolders and
    both unfolders share one polarity command, so reactive current passes the
    zero crossing without the link having to reach zero volts.  The far-side EMF jumps at the line crest so that the steady
    state power changes from p_before to p_after - the converter is not told.
    Control: symmetric "virtual transformer" law, sampled twice per switching
    period, one sample of computation delay.
    """
    ts = 1 / (2 * F_SW)
    sub = 20
    dt = ts / sub
    w = 2 * math.pi * dd.F_LINE
    z = 2 * complex(r_f, w * l_f)
    ph0 = phasor_for_power(v_rms, p_before, z)
    ph1 = phasor_for_power(v_rms, p_after, z)
    if e2_scale_after:
        ph1 = ph0 * e2_scale_after
    t_event = 1.25 / dd.F_LINE
    n_steps = int((t_event + 12e-3) / ts)
    vpk = math.sqrt(2) * v_rms
    k_g = n_active / (2 * F_SW * L_CELL)          # i = v * k_g * D(1-|D|)
    ki = kp / (12 * ts)
    il1 = il2 = v1 = v2 = integ = 0.0     # v1, v2 are LINK voltages (>= 0), il* are AC-side
    d_now = d_next = 0.0
    log = []
    for k in range(n_steps):
        t0 = k * ts
        ph = ph0 if t0 < t_event else ph1
        a2 = math.atan2(ph.imag, ph.real)
        # one polarity decision for BOTH unfolders: zero crossing of the mean port EMF
        pm = 0.5 * (v_rms + ph)
        pol = 1.0 if math.sin(w * t0 + math.atan2(pm.imag, pm.real)) >= 0 else -1.0
        e1 = vpk * math.sin(w * t0)
        e2 = math.sqrt(2) * abs(ph) * math.sin(w * t0 + a2)
        i1 = il1 + (e1 - pol * v1) / r_d          # AC current into port 1
        i2 = il2 + (pol * v2 - e2) / r_d          # AC current out of port 2
        err = v1 - v2
        integ += ki * err * ts
        i_ref = 0.5 * pol * (i1 + i2) + kp * err + integ      # link-frame current
        if i_lim is not None and abs(i_ref) > i_lim:
            integ -= ki * err * ts
            i_ref = math.copysign(i_lim, i_ref)
        vm = max(0.5 * (v1 + v2), 3.0)
        y = max(-0.25, min(0.25, i_ref / (k_g * vm)))
        d_cmd = math.copysign((1 - math.sqrt(1 - 4 * abs(y))) / 2, y)
        d_now, d_next = d_next, d_cmd
        g = k_g * d_now * (1 - abs(d_now))
        for j in range(sub):
            t = t0 + j * dt
            e1 = vpk * math.sin(w * t)
            e2 = math.sqrt(2) * abs(ph) * math.sin(w * t + a2)
            il1 += (e1 - pol * v1 - r_f * il1) / l_f * dt
            il2 += (pol * v2 - e2 - r_f * il2) / l_f * dt
            i1 = il1 + (e1 - pol * v1) / r_d
            i2 = il2 + (pol * v2 - e2) / r_d
            v1 += (pol * i1 - v2 * g) / c_link * dt
            v2 += (v1 * g - pol * i2) / c_link * dt
            v1 = max(v1, -1.5)                    # bridge body diodes clamp the link
            v2 = max(v2, -1.5)
        log.append((t0 + ts, v1, v2, i2, d_now, e1, pol * v2 * i2, pol))
    log = np.array(log)
    post = log[:, 0] > t_event - 0.2e-3
    pre = (log[:, 0] > t_event - 4e-3) & (log[:, 0] < t_event)
    worst = float(np.abs(log[post, 1] - log[post, 2]).max())
    steady = float(np.abs(log[pre, 1] - log[pre, 2]).max())
    last = log[:, 0] > log[-1, 0] - 1 / dd.F_LINE / 2
    p_end = float(np.mean(log[last, 6]))
    if plot_ax is not None:
        tt = (log[:, 0] - t_event) * 1e3
        s = tt > -3.0
        plot_ax.plot(tt[s], log[s, 1] * log[s, 7], lw=1.0, label="port-1 voltage, V")
        plot_ax.plot(tt[s], log[s, 2] * log[s, 7], "--", lw=1.0, label="port-2 voltage, V")
        plot_ax.plot(tt[s], log[s, 3] * (0.25 if abs(log[s, 3]).max() > 1000 else 1.0), lw=1.0,
                     label="port-2 current, A" + (" x0.25" if abs(log[s, 3]).max() > 1000 else ""))
        plot_ax.plot(tt[s], (log[s, 1] - log[s, 2]) * 10, lw=0.8, label="(v1 - v2) x10, V")
        plot_ax.set_title(label, fontsize=9)
        plot_ax.set_xlabel("time after event, ms")
        plot_ax.grid(alpha=0.3)
        plot_ax.legend(fontsize=6, loc="upper right")
    return dict(case=label, worst_dev_V=worst, worst_dev_pct=100 * worst / vpk, steady_dev_V=steady,
                p_end=p_end, i_max=float(np.abs(log[post, 3]).max()))


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    print(f"Selected: {F_SW/1e3:.0f} kHz, {N_CELLS} cells, L per cell = {L_CELL*1e9:.0f} nH\n")
    fig, ax = plt.subplots(1, 2, figsize=(12, 4))
    print("A. switched-waveform check (quarter line cycle, by symmetry)")
    for (v, p, n), a in zip(((120, 60e3, 2), (240, 10e3, 1)), ax):
        r = switched_check(v, p, n, a)
        print(f"  {v:>3} V  set {r['p_set']/1e3:6.1f} kW  simulated {r['p_sim']/1e3:6.2f} kW   "
              f"Irms/cell model {r['i_rms_model']:6.1f} A  simulated {r['i_rms_sim']:6.1f} A   D = {r['d']:.4f}")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "waveforms.png"), dpi=130)

    print("\nB. unannounced events at the line crest (far-side EMF jumps, converter not told)")
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.2))
    cases = [
        dict(v_rms=240, p_before=10e3, p_after=-10e3, n_active=1, label="240 V: +10 kW -> -10 kW, 1 cell"),
        dict(v_rms=240, p_before=100e3, p_after=-100e3, n_active=2, l_f=15e-6, r_f=5e-3, r_d=0.6,
             label="240 V: +100 kW -> -100 kW, 2 cells"),
        dict(v_rms=120, p_before=60e3, p_after=-60e3, n_active=2, l_f=15e-6, r_f=5e-3, r_d=0.6,
             label="120 V: +60 kW -> -60 kW, 2 cells"),
    ]
    for kw, a in zip(cases, ax):
        r = reversal(plot_ax=a, **kw)
        print(f"  {r['case']:42s} |v1-v2| before {r['steady_dev_V']:5.2f} V, worst after {r['worst_dev_V']:6.2f} V "
              f"({r['worst_dev_pct']:.1f} % of crest); final power {r['p_end']/1e3:7.1f} kW; "
              f"peak current {r['i_max']:.0f} A")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "reversal.png"), dpi=130)


if __name__ == "__main__":
    main()
