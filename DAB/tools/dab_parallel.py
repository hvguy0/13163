#!/usr/bin/env python3
"""
Parallel-sharing simulation: N isolated blocks between two common AC buses.

Each block runs the virtual-transformer law with a virtual series impedance Zv
(droop) and sees only its own sensors.  Blocks differ in leakage inductance,
filter inductance and sensor gain.  An optional slow trim, fed with the bank
average current (what the CAN bus would carry), removes the residual error.

Timeline: bank rated power -> unannounced reversal -> 10 s-class surge.

Run:  python3 dab_parallel.py
"""
import math
import os

import numpy as np

import dab_design as dd

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "img")
F_SW = 70e3
N_CELLS = 2
L_CELL = dd.l_cell_required(F_SW, N_CELLS)

# Block-to-block tolerances (block index 0..4)
TOL_LEAK = [1.10, 0.95, 1.00, 0.90, 1.05]         # leakage inductance
TOL_LF = [1.20, 0.80, 1.00, 1.10, 0.90]           # port filter inductance
TOL_VDIFF = [0.003, -0.003, 0.0, 0.0015, -0.002]  # differential voltage-sense gain error
TOL_I = [1.010, 0.990, 1.000, 1.005, 0.995]       # current-sense gain


def run(n_blk=5, v_rms=240.0, zv_pct=3.0, trim=True, t_rev=0.120, t_surge=0.200, t_end=0.280,
        p_rated=10e3, p_surge=100e3, c_link=40e-6, l_f=30e-6, r_f=10e-3, r_d=1.0,
        l_s=3e-6, r_s=1e-3, c_bus=10e-6, kp=0.6, sub=20):
    ts = 1 / (2 * F_SW)
    dt = ts / sub
    w = 2 * math.pi * dd.F_LINE
    vpk = math.sqrt(2) * v_rms
    i_nom = math.sqrt(2) * p_rated / v_rms                  # rated crest current per block
    zv = zv_pct / 100 * vpk / i_nom                          # ohm
    k_nom = N_CELLS / (2 * F_SW * L_CELL)
    k_act = [k_nom / TOL_LEAK[k] for k in range(n_blk)]
    lf = [l_f * TOL_LF[k] for k in range(n_blk)]
    ki = kp / (12 * ts)
    i_clamp = 1.1 * math.sqrt(2) * dd.I_PEAK
    z_tot = 2 * complex(r_s, w * l_s) + (2 * complex(r_f, w * l_f) + zv) / n_blk

    def ph_for(p):
        return v_rms - (p / v_rms) * z_tot

    plan = [(0.0, ph_for(n_blk * p_rated)), (t_rev, ph_for(-n_blk * p_rated)), (t_surge, ph_for(n_blk * p_surge))]
    r = range(n_blk)
    il1 = [0.0] * n_blk; il2 = [0.0] * n_blk; v1 = [0.0] * n_blk; v2 = [0.0] * n_blk
    integ = [0.0] * n_blk; d_now = [0.0] * n_blk; d_next = [0.0] * n_blk
    tr = [0.0] * n_blk; i_filt = [0.0] * n_blk
    vb1 = vb2 = is1 = is2 = 0.0
    kt = zv * i_nom / (0.6 * vpk * 0.015) if trim else 0.0   # ~15 ms trim time constant
    log = []
    for step in range(int(t_end / ts)):
        t0 = step * ts
        ph = [p for (tt, p) in plan if t0 >= tt][-1]
        a2 = math.atan2(ph.imag, ph.real)
        e2a = math.sqrt(2) * abs(ph)
        pm = 0.5 * (v_rms + ph)
        pol = 1.0 if math.sin(w * t0 + math.atan2(pm.imag, pm.real)) >= 0 else -1.0
        g = [0.0] * n_blk
        i_link_true = [0.0] * n_blk
        for k in r:
            i1 = il1[k] + (vb1 - pol * v1[k]) / r_d
            i2 = il2[k] + (pol * v2[k] - vb2) / r_d
            i_link_true[k] = 0.5 * pol * (i1 + i2)
            i_m = TOL_I[k] * i_link_true[k]
            v1m = v1[k] * (1 + TOL_VDIFF[k] / 2)
            v2m = v2[k] * (1 - TOL_VDIFF[k] / 2)
            vm = max(0.5 * (v1m + v2m), 3.0)
            i_filt[k] += (i_m - i_filt[k]) * ts / 1e-3
            err = (v1m - v2m) - zv * i_m + tr[k] * vm
            integ[k] += ki * err * ts
            i_ref = i_m + kp * err + integ[k]
            if abs(i_ref) > i_clamp:
                integ[k] -= ki * err * ts
                i_ref = math.copysign(i_clamp, i_ref)
            y = max(-0.2275, min(0.2275, i_ref / (k_nom * vm)))      # |D| <= 0.35
            d_cmd = math.copysign((1 - math.sqrt(1 - 4 * abs(y))) / 2, y)
            d_now[k], d_next[k] = d_next[k], d_cmd
            g[k] = k_act[k] * d_now[k] * (1 - abs(d_now[k]))
        if trim:
            mean = sum(i_filt) / n_blk
            for k in r:
                tr[k] -= kt * (i_filt[k] - mean) / i_nom * ts
        for j in range(sub):
            t = t0 + j * dt
            e1 = vpk * math.sin(w * t)
            e2 = e2a * math.sin(w * t + a2)
            s1 = s2 = 0.0
            for k in r:
                a = vb1 - pol * v1[k]
                b = pol * v2[k] - vb2
                il1[k] += (a - r_f * il1[k]) / lf[k] * dt
                il2[k] += (b - r_f * il2[k]) / lf[k] * dt
                i1 = il1[k] + a / r_d
                i2 = il2[k] + b / r_d
                s1 += i1
                s2 += i2
                v1[k] = max(v1[k] + (pol * i1 - v2[k] * g[k]) / c_link * dt, -1.5)
                v2[k] = max(v2[k] + (v1[k] * g[k] - pol * i2) / c_link * dt, -1.5)
            is1 += (e1 - vb1 - r_s * is1) / l_s * dt
            is2 += (vb2 - e2 - r_s * is2) / l_s * dt
            vb1 += (is1 - s1) / c_bus * dt
            vb2 += (s2 - is2) / c_bus * dt
        log.append([t0 + ts, vb1, vb2] + [pol * x for x in i_link_true])
    log = np.array(log)

    def window(t_a, t_b):
        m = (log[:, 0] >= t_a) & (log[:, 0] < t_b)
        if not m.any():
            return None
        rms = np.sqrt(np.mean(log[m, 3:] ** 2, axis=0))
        v_rms_out = float(np.sqrt(np.mean(log[m, 2] ** 2)))
        return dict(rms=rms, spread=float((rms.max() - rms.min()) / rms.mean() * 100),
                    worst_over=float((rms.max() / rms.mean() - 1) * 100), v2_rms=v_rms_out)

    cyc = 1 / dd.F_LINE
    res = dict(zv_ohm=zv, rated=window(t_rev - 2 * cyc, t_rev), reversed=window(t_surge - 2 * cyc, t_surge),
               surge=window(t_end - 2 * cyc, t_end), log=log)
    return res


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    print(f"5 blocks in parallel at 240 V, {F_SW/1e3:.0f} kHz, tolerances: leakage +/-10 %, filter L +/-20 %, "
          f"voltage-difference sensing +/-0.3 %, current sensing +/-1 %\n")
    fig, ax = plt.subplots(1, 2, figsize=(14, 4.2), sharey=True)
    for (label, kw), a in zip((("3 % droop only", dict(trim=False)), ("3 % droop + bank-average trim", dict(trim=True))), ax):
        r = run(**kw)
        print(f"{label}  (Zv = {r['zv_ohm']*1e3:.0f} mohm)")
        for name in ("rated", "reversed", "surge"):
            x = r[name]
            print(f"  {name:9s} block rms A: {np.round(x['rms'], 1)}  spread {x['spread']:5.1f} %  "
                  f"worst block {x['worst_over']:+5.1f} % vs mean  far-bus {x['v2_rms']:.0f} V")
        log = r["log"]
        s = log[:, 0] > 0.08
        for k in range(5):
            a.plot(log[s, 0] * 1e3, log[s, 3 + k], lw=0.8, label=f"block {k+1}")
        a.set_title(label, fontsize=10)
        a.set_xlabel("time, ms   (reversal at 120 ms, surge at 200 ms)")
        a.grid(alpha=0.3)
    ax[0].set_ylabel("block current, A")
    ax[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "parallel_sharing.png"), dpi=130)

    r = run(zv_pct=0.0, trim=False, t_rev=0.06, t_surge=9.0, t_end=0.06)
    x = r["rated"]
    print(f"\nNo droop, no trim (for reference): block rms A {np.round(x['rms'], 1)}  spread {x['spread']:.0f} %")


if __name__ == "__main__":
    main()
