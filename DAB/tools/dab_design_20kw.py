#!/usr/bin/env python3
"""
20 kW-peak variant of both blocks (10 kW continuous unchanged).

With only a 2x surge the switches are no longer sized by the 10 s event.  They
are sized by continuous efficiency and steady-state junction temperature, so
the selection rule here is: lowest cost that keeps
  - junction <= 125 C at the end of the 10 s peak,
  - junction <= 110 C continuously,
  - loss at 10 kW / 85 V within LOSS_85_MAX.  Three tiers are printed: thermal
    minimum, balanced (selected) and matched to the 100 kW-peak design.

Run:  python3 dab_design_20kw.py
"""
import json
import math
import os

import dab_design as dd

# ---- specification override -------------------------------------------------
dd.P_PEAK = 20e3
dd.V_KNEE = 120.0            # 20 kW from 120 V up
dd.I_PEAK = dd.P_PEAK / dd.V_KNEE      # 167 A below that (14 kW at 85 V)
dd.V_D = 85.0                # full peak current available down to 85 V at D = 0.25
LOSS_85_MAX = 600.0           # balanced tier; see the tier table printed by main()
TJ_CONT_MAX = 110.0
F_SEL = 70e3


def check(r):
    tj_c = max(dd.T_SINK_CONT + c["hf_per_switch"] * (r["_kw"]["mod"].rth_jc + r["_kw"]["mod"].rth_cs)
               for c in r["cont"].values())
    tj_u = max(dd.T_SINK_CONT + c["unf_per_switch"] * (r["_kw"]["unf_mod"].rth_jc + r["_kw"]["unf_mod"].rth_cs)
               for c in r["cont"].values())
    ok = (r["tj_hf"] <= dd.TJ_LIMIT and r["tj_unf"] <= dd.TJ_LIMIT and max(tj_c, tj_u) <= TJ_CONT_MAX
          and r["cont"]["85"]["loss"] <= LOSS_85_MAX)
    return ok, max(tj_c, tj_u)


def select(f, verbose=True, mat=1.0):
    best = None
    rows = []
    for n in (1, 2):
        for m_hf in range(2, 13):
            for m_unf in range(2, 13):
                r = dd.evaluate(f, n, dd.DISC.par(m_hf), dd.DISC.par(m_unf), mat=mat)
                if not r["feasible"]:
                    continue
                ok, tj_c = check(r)
                if not ok:
                    continue
                ru = dd.rollup(r)
                rows.append((n, m_hf, m_unf, ru["cost"], r))
                if best is None or ru["cost"] < best[1]["cost"]:
                    best = (r, ru, tj_c, n, m_hf, m_unf)
                break            # larger m_unf only costs more
    if verbose:
        print("cells | HF per group | unfolder per group | devices | block $ | loss 85 V | eta 240 V")
        seen = set()
        for n, m_hf, m_unf, cost, r in sorted(rows, key=lambda x: x[3])[:8]:
            print(f"  {n}   | {m_hf:2d}           | {m_unf:2d}                 | {8*n*m_hf + 8*m_unf:4d}    | {cost:6.0f}  | "
                  f"{r['cont']['85']['loss']:5.0f} W   | {r['cont']['240']['eff']*100:.2f} %")
    return best


def main():
    out = {"spec": dict(p_cont=dd.P_CONT, p_peak=dd.P_PEAK, i_peak=dd.I_PEAK, v_knee=dd.V_KNEE)}
    print(f"Peak envelope: {dd.P_PEAK/1e3:.0f} kW down to {dd.V_KNEE:.0f} V, {dd.I_PEAK:.0f} A below "
          f"({dd.V_MIN*dd.I_PEAK/1e3:.1f} kW at {dd.V_MIN:.0f} V)\n")
    global LOSS_85_MAX
    print("=== Isolated block: device count against low-line efficiency, 70 kHz ===")
    keep = LOSS_85_MAX
    tiers = []
    for name, cap in (("thermal minimum", 5000.0), ("balanced", keep), ("matched to 100 kW design", 400.0)):
        LOSS_85_MAX = cap
        rr, rru, tjc, nn, mh, mu = select(F_SEL, verbose=False)
        pk = max(p["loss"] for p in rr["peak"].values())
        tiers.append(dict(tier=name, cells=nn, hf=mh, unf=mu, devices=8 * nn * mh + 8 * mu, cost=rru["cost"],
                          volume_L=rru["volume_L"], mass_kg=rru["mass_kg"], tj_cont=tjc,
                          tj_peak=max(rr["tj_hf"], rr["tj_unf"]), peak_loss=pk,
                          eff={v: rr["cont"][v]["eff"] for v in ("85", "120", "240")}))
        print(f"  {name:26s} {8*nn*mh + 8*mu:3d} devices (HF {mh}, unfolder {mu} per group)  ${rru['cost']:.0f}  {rru['volume_L']:.0f} L  "
              f"{rru['mass_kg']:.0f} kg | eta 85/120/240 V: {rr['cont']['85']['eff']*100:.2f} / {rr['cont']['120']['eff']*100:.2f} / "
              f"{rr['cont']['240']['eff']*100:.2f} % | Tj cont {tjc:.0f} C, peak {max(rr['tj_hf'], rr['tj_unf']):.0f} C | peak loss {pk:.0f} W")
    out["tiers"] = tiers
    LOSS_85_MAX = keep
    print()
    r, ru, tj_c, n, m_hf, m_unf = select(F_SEL)
    print(f"\nSelected: {n} cell(s), {m_hf} per HF group, {m_unf} per unfolder group, "
          f"{8*n*m_hf + 8*m_unf} devices, L = {r['l_cell_nH']:.0f} nH, continuous Tj {tj_c:.0f} C")

    print("\n=== Frequency evaluation (selection repeated at each frequency) ===")
    print("f kHz | cells | devices | L nH | transformer            | xf kg | eta10@240 | eta10@85 | block $")
    sweep = []
    for f in (50e3, 70e3, 100e3, 140e3, 200e3, 300e3):
        b = select(f, verbose=False, mat=1.0 if f < 250e3 else 0.45)
        if b is None:
            print(f"{f/1e3:5.0f} | no option meets the limits")
            continue
        rr, rru, _, nn, mh, mu = b
        x = rr["xf"]
        print(f"{f/1e3:5.0f} | {nn}     | {8*nn*mh + 8*mu:4d}    | {rr['l_cell_nH']:4.0f} | {x['stack']}x {x['core']:12s} {x['n']:2d} turns | "
              f"{x['mass_kg']:.2f}  | {rr['cont']['240']['eff']*100:.2f}     | {rr['cont']['85']['eff']*100:.2f}    | {rru['cost']:.0f}")
        d = {k: v for k, v in rr.items() if not k.startswith("_")}
        d["peak_loss"] = max(p["loss"] for p in rr["peak"].values())
        d["cost"] = rru["cost"]
        sweep.append(d)
    out["freq_sweep"] = sweep

    x = r["xf"]
    print("\n=== Transformer ===")
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in x.items()}, indent=1))
    w = [6, 6, 7, 7, 8, 8, 8, 6, 7, 7, 8, 8, 8]
    for label, key in (("10 kW continuous", "cont"), ("2.5 kW", "part"), ("10 s peak", "peak")):
        print(f"\n-- {label} --")
        print(dd.fmt_row(["Vrms", "cells", "D", "P kW", "Itr", "HF cond", "HF sw", "gate", "xf cu", "xf fe", "unfold", "loss W", "eta %"], w))
        for v in dd.V_GRID:
            c = r[key][str(int(v))]
            print(dd.fmt_row([int(v), c["n_active"], f"{c['d']:.4f}", f"{c['p']/1e3:.1f}", f"{c['i_tr']:.0f}", f"{c['hf_cond']:.0f}",
                              f"{c['hf_sw']:.0f}", f"{c['gate']:.0f}", f"{c['xf_cu']:.0f}", f"{c['xf_fe']:.0f}", f"{c['unf']:.0f}",
                              f"{c['loss']:.0f}", f"{c['eff']*100:.2f}"], w))
            if key == "peak":
                print(f"       Tj HF {c['tj_hf']:.0f} C, Tj unfolder {c['tj_unf']:.0f} C")
    print(f"\n=== Roll-up, isolated block (heatsink {ru['m_sink']:.1f} kg) ===")
    for k, v in ru["items"].items():
        print(f"  {k:38s} ${v[0]:7.0f}  {v[1]:5.1f} L  {v[2]:5.1f} kg")
    print(f"  TOTAL  ${ru['cost']:.0f}   {ru['volume_L']:.1f} L enclosure   {ru['mass_kg']:.1f} kg")
    out["isolated"] = {k: v for k, v in r.items() if not k.startswith("_")}
    out["isolated_rollup"] = ru

    print("\n=== Non-isolated chopper, 120 V <-> 277 / 230 V ===")
    print("ratio       | f kHz | devices | Tj pk | 10 kW loss / eta | 2.5 kW eta | 20 kW loss / eta")
    chop = {}
    for v_hi in (277.0, 230.0):
        for f in (50e3, 70e3, 100e3):
            c = dd.chopper(120.0, v_hi, f)
            print(f"120 <-> {v_hi:.0f} | {f/1e3:5.0f} | {c['devices']:4d}    | {c['tj']:4.0f}  | {c['cont']['loss']:4.0f} W / {c['cont']['eff']*100:.2f} % | "
                  f"{c['part']['eff']*100:.2f} %    | {c['peak']['loss']:4.0f} W / {c['peak']['eff']*100:.2f} %")
            if f == F_SEL:
                chop[str(int(v_hi))] = c
    ni = max(chop.values(), key=lambda c: c["devices"])
    print("  10 kW split at 277 V, 70 kHz: " + ", ".join(f"{k} {v:.0f}" for k, v in chop["277"]["cont"].items() if k not in ("loss", "eff")))
    # gapped-ferrite inductor check on the same core as the transformer (2x E100/60/28)
    ae, i_pk, n_t = 1476e-6, math.sqrt(2) * dd.I_PEAK * 1.15, 12
    print(f"  inductor on 2x E100/60/28: {n_t} turns, gap {dd.MU0*n_t**2*ae/dd.CHOP_L*1e3:.1f} mm, "
          f"B = {dd.CHOP_L*i_pk/(n_t*ae)*1e3:.0f} mT at {i_pk:.0f} A")
    print(f"\n=== Roll-up, non-isolated block ({ni['m']} per group, {ni['devices']} devices, heatsink {ni['m_sink']:.1f} kg) ===")
    for k, v in ni["items"].items():
        print(f"  {k:38s} ${v[0]:7.0f}  {v[1]:5.1f} L  {v[2]:5.1f} kg")
    print(f"  TOTAL  ${ni['cost']:.0f}   {ni['volume_L']:.1f} L enclosure   {ni['mass_kg']:.1f} kg")
    out["chopper"] = chop

    print("\n=== Scaling ===")
    for label, blocks in (("1-phase block", 1), ("3-phase bank", 3), ("3-phase, 5 in parallel", 15)):
        kv, km = (1.0, 1.0) if blocks == 1 else (1.15, 1.08)
        print(f"  {label:24s} {dd.P_CONT*blocks/1e3:4.0f} kW cont {dd.P_PEAK*blocks/1e3:4.0f} kW peak | isolated {ru['volume_L']*blocks*kv:4.0f} L "
              f"{ru['mass_kg']*blocks*km:4.0f} kg ${ru['cost']*blocks:6.0f} | chopper {ni['volume_L']*blocks*kv:4.0f} L "
              f"{ni['mass_kg']*blocks*km:4.0f} kg ${ni['cost']*blocks:6.0f}")
    with open(os.path.join(dd.OUT, "results_20kw.json"), "w") as fh:
        json.dump(out, fh, indent=1, default=lambda o: float(o) if hasattr(o, "__float__") else str(o))
    dd.make_plots(out, r, suffix="_20kw")


if __name__ == "__main__":
    main()
