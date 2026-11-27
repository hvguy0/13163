#!/usr/bin/env python3
"""
Non-isolated block (bidirectional AC chopper, 120 V <-> 277/230 V) redesigned
to meet an efficiency target of 99.06 % at 35 % load.

Efficiency is taken the way transformer standards define it:
    eta = P_out / (P_out + P_loss)   at P_out = 35 % of the 10 kW rating,
so the whole block may lose at most 33.2 W at 3.5 kW.

That budget forces three changes to the earlier chopper model, all made here:
  1. Soft switching at light load.  The inductor ripple is made larger than the
     load current so the current reverses every cycle and the switches turn on
     at zero voltage; the switching frequency rises above 50 kHz as needed to
     hold that boundary, and returns to 50 kHz (hard-switched) at high load.
  2. Every series resistance is counted: switches, inductor, capacitors' ESR,
     both EMI chokes (line and neutral windings), fuses, contactors, busbars.
  3. Standby power is budgeted item by item instead of a flat 25 W.

Run:  python3 chopper_doe.py
"""
import json
import math
import os

import numpy as np

import dab_design as dd
import dab_cost as dc                     # 20 kW-peak spec, device table, cost model

TARGET = 0.9906
DESIGN_TO = 0.9920        # design aim: about 5 W of margin at the 35 % point
LOAD_FRAC = 0.35
V_LO = 120.0
RATIOS = (277.0, 230.0)
F_MIN = 50e3
TH = np.linspace(0, math.pi, 361)[1:-1]
SIN = np.sin(TH)

# ---- loss budget constants (all EST; these become design requirements) ------
R_PATH_LV = 3.0e-3      # ohm: fuse + contactor + both EMI-choke windings + busbar, 120 V side
R_PATH_HV = 6.0e-3      # ohm: same on the high-voltage side
ESR_CAP = 3.0e-3        # ohm, C1 and C2 each
FR_RIPPLE = 3.0         # ac/dc resistance of the inductor winding for the ripple current
GATE_SUPPLY_EFF = 0.85
T_RISE = 15e-9          # s, hard turn-on voltage/current overlap
STANDBY = {             # W, always on
    "controller, sensing, comms": 2.5,
    "isolated gate supplies (quiescent)": 0.6,
    "contactor coils (economised hold, 2)": 1.4,
    "aux supply loss": 1.0,
}
P_FAN = 6.0             # W, only when the block dissipates more than FAN_ON
FAN_ON = 80.0

# inductor on stacked E100/60/28 ferrite sets
AE1, VE1 = 738e-6, 202e-6
WINDOW = 22.8e-3 * 93.7e-3
B_MAX = 0.30
K_CU = 0.30


def inductor(l, stacks):
    ae, ve = AE1 * stacks, VE1 * stacks
    i_pk = math.sqrt(2) * dd.I_PEAK + math.sqrt(2) * V_LO * (1 - V_LO / max(RATIOS)) / (F_MIN * l) / 2
    n = math.ceil(l * i_pk / (B_MAX * ae))
    a_cu = K_CU * WINDOW / n
    mlt = 2 * (27.5e-3 + 27.5e-3 * stacks) + math.pi * 22.8e-3
    rdc = dd.rho_cu(60.0) * n * mlt / a_cu
    return dict(l=l, stacks=stacks, n=n, ae=ae, ve=ve, rdc=rdc, i_pk=i_pk,
                gap_mm=dd.MU0 * n * n * ae / l * 1e3, mass=ve * 4850 + n * mlt * a_cu * 8960,
                a_cu_mm2=a_cu * 1e6)


def losses(mod, m, ind, p_out, v_hi, f, tj):
    """Loss breakdown at one operating point and one switching frequency."""
    duty = V_LO / v_hi
    v = math.sqrt(2) * v_hi * SIN                       # switched voltage
    i_avg = math.sqrt(2) * p_out / V_LO * SIN           # inductor average current
    dlt = (V_LO * math.sqrt(2) * SIN) * (1 - duty) / (f * ind["l"])   # peak-to-peak ripple
    i_pk, i_val = i_avg + dlt / 2, i_avg - dlt / 2
    i2_avg, i2_rip = float(np.mean(i_avg ** 2)), float(np.mean(dlt ** 2 / 12))
    q = mod.qoss(v)
    # turn-off of the control switch at the current peak (capacitively snubbed)
    e_off = dd.e_off(mod, v, i_pk)
    # turn-off of the synchronous switch at a negative valley
    e_off2 = np.where(i_val < 0, dd.e_off(mod, v, np.abs(i_val)), 0.0)
    # turn-on of the control switch at the valley
    need = q * v
    avail = 0.5 * ind["l"] * np.minimum(i_val, 0.0) ** 2
    resid = np.clip(1 - avail / np.maximum(need, 1e-12), 0, 1)
    e_on = resid * need + 0.5 * v * np.maximum(i_val, 0.0) * T_RISE
    parts = {
        "switch conduction": 2 * mod.rds(tj) * (i2_avg + i2_rip),
        "switching": f * float(np.mean(e_off + e_off2 + e_on)),
        "gate drive": 2 * mod.qg * dd.V_GATE_SWING * f / GATE_SUPPLY_EFF,
        "inductor copper": ind["rdc"] * (i2_avg + FR_RIPPLE * i2_rip),
        "inductor core": dd.pv_core(f, ind["l"] * float(dlt.max()) / 2 / (ind["n"] * ind["ae"])) * dd.ENV_FACTOR * ind["ve"],
        "capacitor ESR": ESR_CAP * (duty * (1 - duty) * (i2_avg + i2_rip) + i2_rip),
        "fuses, contactors, EMI chokes, bus": R_PATH_LV * (p_out / V_LO) ** 2 + R_PATH_HV * (p_out / v_hi) ** 2,
        "standby": sum(STANDBY.values()),
    }
    tot = sum(parts.values())
    if tot > FAN_ON:
        parts["fans"] = P_FAN
        tot += P_FAN
    parts["total"] = tot
    parts["zvs_fraction"] = float(np.mean(resid < 0.02))
    return parts


def best_f(mod, m, ind, p_out, v_hi, tj):
    """Controller picks the frequency (>= 50 kHz) that minimises loss at this point."""
    best = None
    for f in np.arange(F_MIN, 200e3 + 1, 5e3):
        r = losses(mod, m, ind, p_out, v_hi, f, tj)
        if best is None or r["total"] < best[1]["total"]:
            best = (float(f), r)
    return best


def evaluate(base, m, l, stacks):
    mod = base.par(m)
    ind = inductor(l, stacks)
    res = dict(base=base.name, m=m, l=l, stacks=stacks, ind=ind, pts={})
    worst_eta = 1.0
    for v_hi in RATIOS:
        f35, p35 = best_f(mod, m, ind, LOAD_FRAC * dd.P_CONT, v_hi, 50.0)
        eta = LOAD_FRAC * dd.P_CONT / (LOAD_FRAC * dd.P_CONT + p35["total"])
        f100, p100 = best_f(mod, m, ind, dd.P_CONT, v_hi, 80.0)
        # 10 s peak at 50 kHz, junction temperature self-consistent
        tj = 100.0
        for _ in range(10):
            pk = losses(mod, m, ind, V_LO * dd.I_PEAK, v_hi, F_MIN, tj)
            duty = V_LO / v_hi
            p_grp = max(duty, 1 - duty) * pk["switch conduction"] / 2 + pk["switching"]
            tj = min(dd.T_SINK_CONT + dd.DT_SINK_PEAK + p_grp * (mod.rth_jc + mod.rth_cs), 400.0)
        res["pts"][str(int(v_hi))] = dict(f35=f35, p35=p35, eta35=eta, f100=f100, p100=p100,
                                          eta100=dd.P_CONT / (dd.P_CONT + p100["total"]), peak=pk, tj_pk=tj)
        worst_eta = min(worst_eta, eta)
    res["eta35"] = worst_eta
    res["tj_pk"] = max(p["tj_pk"] for p in res["pts"].values())
    n_drv = 4 * math.ceil(m / 8)
    fixed = dict(dc.FIX_CHOP)
    fixed["Inductor"] = (160 + 60 * (stacks - 2), 70 + 25 * (stacks - 2))
    semis_pk = max(p["peak"]["switch conduction"] + p["peak"]["switching"] for p in res["pts"].values())
    m_sink = dd.sink_mass(max(2.0, semis_pk * dd.T_PEAK / (900 * dd.DT_SINK_PEAK)), 60.0)
    items, n_dev = dc.bom([(mod, 4)], 0, None, m_sink, fixed)
    items["Gate drives"] = (18 * n_drv, 9 * n_drv)
    res.update(items=items, devices=n_dev, k1=sum(v[1] for v in items.values()), proto=sum(v[0] for v in items.values()))
    return res


def main():
    budget = LOAD_FRAC * dd.P_CONT * (1 / TARGET - 1)
    print(f"Target {TARGET*100:.2f} % at {LOAD_FRAC*100:.0f} % load -> at most {budget:.1f} W total loss at {LOAD_FRAC*dd.P_CONT/1e3:.1f} kW\n")
    # where the earlier cost-optimised chopper stands under this stricter loss model
    old = evaluate(dc.D40, 6, 20e-6, 2)
    print(f"Cost-optimised chopper (6 x 40 mohm, 20 uH), fixed 50 kHz, with its original 25 W standby: about "
          f"{100*3500/(3500 + losses(dc.D40.par(6), 6, old['ind'], 3500, 277.0, 50e3, 50.0)['total'] - sum(STANDBY.values()) + 25):.2f} % at 35 % load\n")
    rows = []
    for base, ms in ((dc.D40, (6, 8, 10, 12, 16, 20, 24)), (dc.D16, (3, 4, 5, 6, 8, 10))):
        for m in ms:
            for l in (8e-6, 10e-6, 12e-6, 14e-6, 16e-6, 18e-6, 20e-6, 25e-6):
                for stacks in (2, 3):
                    r = evaluate(base, m, l, stacks)
                    if r["tj_pk"] <= dd.TJ_LIMIT:
                        rows.append(r)
    ok = [r for r in rows if r["eta35"] >= TARGET]
    print(f"{len(rows)} thermally valid designs, {len(ok)} meet the target at both ratios")
    print("\n=== Cheapest designs at each efficiency level (worse of 277 V and 230 V) ===")
    print("eta35 %  | 1k $  | proto $ | per group            | L uH | core | devices")
    best, seen = float("inf"), []
    for r in sorted(rows, key=lambda r: -r["eta35"]):
        if r["k1"] < best - 1:
            best = r["k1"]
            seen.append(r)
    for r in seen[:14]:
        print(f"{r['eta35']*100:.3f}   | {r['k1']:5.0f} | {r['proto']:6.0f}  | {r['m']:2d} x {r['base']:17s} | {r['l']*1e6:4.0f} | {r['stacks']}x   | {r['devices']}"
              + ("   <- meets target" if r["eta35"] >= TARGET else ""))
    # selection: cheapest design reaching DESIGN_TO (target plus margin for the estimated inputs)
    cand = [r for r in rows if r["eta35"] >= DESIGN_TO] or ok
    if not cand:
        print("\nNo design in the search meets the target.")
        return
    sel = min(cand, key=lambda r: (round(r["k1"]), -r["eta35"]))
    ind = sel["ind"]
    print(f"\n=== Selected: {sel['m']} x {sel['base']} per group ({sel['devices']} devices), L1 = {ind['l']*1e6:.0f} uH ===")
    print(f"  inductor: {ind['stacks']} stacked E100/60/28 sets, {ind['n']} turns, {ind['a_cu_mm2']:.0f} mm^2 litz, gap {ind['gap_mm']:.1f} mm, "
          f"Rdc {ind['rdc']*1e3:.2f} mohm, {ind['mass']:.1f} kg, {B_MAX*1e3:.0f} mT at {ind['i_pk']:.0f} A")
    for v_hi, p in sel["pts"].items():
        print(f"\n  120 V <-> {v_hi} V")
        print(f"    35 % load: {p['eta35']*100:.3f} %  ({p['p35']['total']:.1f} W, {p['f35']/1e3:.0f} kHz, zero-voltage turn-on over {p['p35']['zvs_fraction']*100:.0f} % of the line cycle)")
        print(f"    100 % load: {p['eta100']*100:.2f} %  ({p['p100']['total']:.0f} W, {p['f100']/1e3:.0f} kHz)")
        print(f"    20 kW peak: {p['peak']['total']:.0f} W, junction {p['tj_pk']:.0f} C")
    p = sel["pts"]["277"]["p35"]
    q = sel["pts"]["277"]["p100"]
    print("\n  Loss budget, 120 <-> 277 V            35 % load    100 % load")
    for k in p:
        if k not in ("total", "zvs_fraction"):
            print(f"    {k:36s} {p[k]:6.1f} W    {q.get(k, 0):6.1f} W")
    print(f"    {'fans':36s} {p.get('fans', 0):6.1f} W    {q.get('fans', 0):6.1f} W")
    print(f"    {'TOTAL':36s} {p['total']:6.1f} W    {q['total']:6.1f} W")
    print("\n  Standby detail: " + ", ".join(f"{k} {v} W" for k, v in STANDBY.items()))
    print("\n  Cost                                 proto        1k")
    dc.show_items(sel["items"])

    # efficiency curve and sensitivity
    mod = sel["base"] == dc.D40.name and dc.D40.par(sel["m"]) or dc.D16.par(sel["m"])
    print("\n  Efficiency against load (120 <-> 277 V):")
    curve = []
    for frac in (0.1, 0.2, 0.35, 0.5, 0.75, 1.0):
        f, r = best_f(mod, sel["m"], ind, frac * dd.P_CONT, 277.0, 50.0 if frac < 0.6 else 80.0)
        eta = frac * dd.P_CONT / (frac * dd.P_CONT + r["total"])
        curve.append((frac, eta, f, r["total"]))
        print(f"    {frac*100:4.0f} %: {eta*100:.2f} %  ({r['total']:.0f} W, {f/1e3:.0f} kHz)")
    print("\n  Sensitivity of the 35 % point (277 V): what each assumption is worth")
    f35 = sel["pts"]["277"]["f35"]
    base_loss = sel["pts"]["277"]["p35"]["total"]
    for name, dw in (("standby +3 W", 3.0), ("path resistance +50 %", 0.5 * p["fuses, contactors, EMI chokes, bus"]),
                     ("on-resistance +20 %", 0.2 * p["switch conduction"]), ("switching loss x2", p["switching"]),
                     ("inductor loss +50 %", 0.5 * (p["inductor copper"] + p["inductor core"]))):
        print(f"    {name:26s} -> {100*3500/(3500 + base_loss + dw):.3f} %")
    out = dict(target=TARGET, budget_W=budget, selected={k: v for k, v in sel.items() if k != "items"},
               items=sel["items"], curve=curve)
    with open(os.path.join(dd.OUT, "results_doe.json"), "w") as fh:
        json.dump(out, fh, indent=1, default=lambda o: float(o) if hasattr(o, "__float__") else str(o))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 4.4))
    fr = np.linspace(0.05, 1.0, 40)
    for v_hi in RATIOS:
        e = []
        for x in fr:
            _, r = best_f(mod, sel["m"], ind, x * dd.P_CONT, v_hi, 50.0 if x < 0.6 else 80.0)
            e.append(100 * x * dd.P_CONT / (x * dd.P_CONT + r["total"]))
        a.plot(fr * 100, e, label=f"120 <-> {v_hi:.0f} V")
    a.axhline(TARGET * 100, color="C3", ls="--", lw=1)
    a.axvline(35, color="C3", ls="--", lw=1)
    a.plot([35], [TARGET * 100], "o", color="C3", label="target: 99.06 % at 35 % load")
    a.set_ylim(97.5, 99.6)
    a.set_xlabel("load, % of 10 kW")
    a.set_ylabel("efficiency, %")
    a.set_title("Redesigned non-isolated block")
    a.grid(alpha=0.3)
    a.legend(fontsize=8)
    keys = [k for k in p if k not in ("total", "zvs_fraction", "fans")]
    b.barh(range(len(keys)), [p[k] for k in keys])
    b.set_yticks(range(len(keys)), keys, fontsize=8)
    b.invert_yaxis()
    b.set_xlabel("W at 35 % load (120 <-> 277 V)")
    b.set_title(f"Where the {p['total']:.1f} W goes (limit {budget:.1f} W)")
    b.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(dd.OUT, "img", "doe_efficiency.png"), dpi=130)


if __name__ == "__main__":
    main()
