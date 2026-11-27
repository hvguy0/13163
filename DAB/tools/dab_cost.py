#!/usr/bin/env python3
"""
Cost optimisation of the 10 kW / 20 kW-peak blocks, with prototype-quantity and
1000-unit cost columns.

Searches SiC die size (16 / 40 / 75 mOhm), devices per group, switching
frequency (50 / 70 kHz) and transformer recipe (efficiency- or cost-oriented),
keeps only thermally valid designs, and prints the cost-versus-efficiency
frontier.

Cost = bill of materials + assembly and test.  It excludes NRE, certification,
warranty, logistics and margin.  Device prices for the 40 and 75 mOhm parts are
anchored to distributor listings; everything else is EST.

Run:  python3 dab_cost.py
"""
import json
import math
import os

import dab_design as dd
import dab_design_20kw as t20          # applies the 20 kW-peak specification to dd

dd.IM_BUCKET = 8.0
TJ_CONT_MAX = 110.0
MAX_PAR_HF = 8        # most devices paralleled per group where they switch at 50-70 kHz (layout limit)
MAX_PAR_LF = 12       # line-frequency unfolder groups can parallel more

#                      name                         rds    tc      rth_jc qoss400  qg       proto$  rth_cs
D16 = dd.Module("16 mOhm TO-247-4", 16e-3, 0.0055, 0.27, 0.20e-6, 0.21e-6, 38.0, rth_cs=0.45)
D40 = dd.Module("40 mOhm TO-247-4", 40e-3, 0.0055, 0.46, 0.09e-6, 0.099e-6, 12.0, rth_cs=0.45)
D75 = dd.Module("75 mOhm TO-247-4", 75e-3, 0.0055, 0.80, 0.05e-6, 0.054e-6, 8.0, rth_cs=0.45)
PRICE_1K = {16e-3: 26.0, 40e-3: 6.5, 75e-3: 4.4}      # USD each at 1000 units
M_RANGE = {16e-3: range(2, 9), 40e-3: range(3, 17), 75e-3: range(6, 31, 2)}
LITZ = {0.05: (160.0, 95.0), 0.071: (110.0, 60.0), 0.1: (75.0, 38.0)}   # USD/kg (proto, 1k)

# fixed items: (prototype, 1k)
FIX_ISO = {
    "Link capacitors": (56, 28), "EMI filters (2 ports)": (500, 220), "Contactors, fuses, surge": (350, 160),
    "Sensing, control, aux supply": (550, 190), "PCBs, busbars, enclosure": (550, 230),
}
FIX_CHOP = {
    "Inductor": (160, 70), "Port capacitors, snubber": (60, 25), "Low-side crowbar": (150, 45),
    "EMI filters (2 ports)": (380, 160), "Contactors, fuses, surge": (350, 130),
    "Sensing, control, aux supply": (550, 190), "PCBs, busbars, enclosure": (400, 180),
}


def dev_price(mod):
    base = mod.rds25 * mod.n_par
    return mod.cost_sw / mod.n_par, PRICE_1K[min(PRICE_1K, key=lambda k: abs(k - base))]


def xf_cost(x):
    lp, lk = LITZ[round(x["strand_mm"], 3)]
    return (x["m_core_kg"] * 25 + x["m_cu_kg"] * lp + 120, x["m_core_kg"] * 11 + x["m_cu_kg"] * lk + 40)


def bom(groups, n_xf, xf, m_sink, fixed, gate_each=(18, 9)):
    """groups: list of (paralleled Module, number of groups).  Returns {item: (proto, 1k)}."""
    n_dev = sum(m.n_par * g for m, g in groups)
    n_grp = sum(g for _, g in groups)
    sw_p = sum(dev_price(m)[0] * m.n_par * g for m, g in groups)
    sw_k = sum(dev_price(m)[1] * m.n_par * g for m, g in groups)
    items = {"SiC switches": (sw_p, sw_k), "Gate drives": (gate_each[0] * n_grp, gate_each[1] * n_grp)}
    if n_xf:
        xp, xk = xf_cost(xf)
        items["Transformer"] = (xp * n_xf, xk * n_xf)
    items["Heatsink and fans"] = (12 * m_sink + 60, 6 * m_sink + 25)
    items.update(fixed)
    items["Assembly and test"] = (2.5 * n_dev + 300, 1.2 * n_dev + 110)
    return items, n_dev


def unf_eval(u):
    tj = 100.0
    for _ in range(12):
        p_sw = u.rds(tj) * dd.I_PEAK ** 2 / 2
        tj = min(dd.T_SINK_CONT + dd.DT_SINK_PEAK + p_sw * (u.rth_jc + u.rth_cs), 400.0)
    cont = {str(int(v)): dd.unfolder_loss(u, 1, dd.P_CONT / v, 80.0)[0] for v in dd.V_GRID}
    tj_c = dd.T_SINK_CONT + cont["85"] / 8 * (u.rth_jc + u.rth_cs)
    return dict(tj_pk=tj, tj_cont=tj_c, cont=cont, peak=8 * p_sw)


def search_isolated():
    unf_opts = [(base.par(m), None) for base in (D16, D40, D75) for m in M_RANGE[base.rds25] if m <= MAX_PAR_LF]
    unf_opts = [(u, unf_eval(u)) for u, _ in unf_opts]
    unf_opts = [(u, e) for u, e in unf_opts if e["tj_pk"] <= dd.TJ_LIMIT and e["tj_cont"] <= TJ_CONT_MAX]
    ref = D16.par(6)
    ref_e = unf_eval(ref)
    rows = []
    for recipe, strands, wkg in (("efficiency", (0.05e-3, 0.071e-3, 0.10e-3), 4.0), ("cost", (0.10e-3,), 12.0)):
        dd.STRANDS, dd.W_PER_KG = strands, wkg
        for f in (50e3, 70e3):
            for base in (D16, D40, D75):
                for m in (m for m in M_RANGE[base.rds25] if m <= MAX_PAR_HF):
                    hf = base.par(m)
                    r = dd.evaluate(f, 1, hf, ref)
                    if not r["feasible"] or r["tj_hf"] > dd.TJ_LIMIT:
                        continue
                    tj_c = max(dd.T_SINK_CONT + c["hf_per_switch"] * (hf.rth_jc + hf.rth_cs) for c in r["cont"].values())
                    if tj_c > TJ_CONT_MAX:
                        continue
                    hf_pk = max(p["hf_cond"] + p["hf_sw"] for p in r["peak"].values())
                    for u, e in unf_opts:
                        loss = {v: r["cont"][v]["loss"] - ref_e["cont"][v] + e["cont"][v] for v in r["cont"]}
                        semis85 = r["cont"]["85"]["hf_cond"] + r["cont"]["85"]["hf_sw"] + e["cont"]["85"]
                        m_sink = dd.sink_mass(max(3.0, (hf_pk + e["peak"]) * dd.T_PEAK / (900 * dd.DT_SINK_PEAK)), semis85)
                        items, n_dev = bom([(hf, 8), (u, 8)], 1, r["xf"], m_sink, FIX_ISO)
                        rows.append(dict(recipe=recipe, f=f, hf=hf.name, unf=u.name, devices=n_dev,
                                         proto=sum(v[0] for v in items.values()), k1=sum(v[1] for v in items.values()),
                                         loss=loss, typ=(loss["120"] + loss["208"] + loss["240"]) / 3,
                                         tj_pk=max(r["tj_hf"], e["tj_pk"]), tj_cont=max(tj_c, e["tj_cont"]),
                                         m_sink=m_sink, items=items, xf=r["xf"],
                                         peak_loss=max(p["loss"] - p["unf"] for p in r["peak"].values()) + e["peak"]))
    return rows


def search_chopper():
    rows = []
    for f in (50e3, 70e3):
        for base in (D16, D40, D75):
            for m in (m for m in M_RANGE[base.rds25] if m <= MAX_PAR_HF):
                d = base.par(m)
                worst = None
                for v_hi in (277.0, 230.0):
                    duty = 120.0 / v_hi
                    vpk = math.sqrt(2) * v_hi

                    def p_sw(i_rms, mm, vpk=vpk, f=f, base=base):
                        hard = 0.5 * f * dd.E_SW_REF * (vpk / 400.0) * (math.sqrt(2) * i_rms / 50.0)
                        return hard + 0.6 * f * mm * dd.E_OSS_REF * (16e-3 / base.rds25) * (vpk / 400.0) ** 1.5

                    tj = 100.0
                    for _ in range(12):
                        p_grp = max(duty, 1 - duty) * d.rds(tj) * dd.I_PEAK ** 2 + p_sw(dd.I_PEAK, m)
                        tj = min(dd.T_SINK_CONT + dd.DT_SINK_PEAK + p_grp * (d.rth_jc + d.rth_cs), 400.0)
                    c = dd._chop_loss(d, m, dd.P_CONT, 70.0, 120.0, duty, f, p_sw)
                    pk = dd._chop_loss(d, m, 120.0 * dd.I_PEAK, tj, 120.0, duty, f, p_sw)
                    tj_c = dd.T_SINK_CONT + (max(duty, 1 - duty) * c["cond"] / 2 + c["sw"]) * (d.rth_jc + d.rth_cs)
                    cand = dict(tj=tj, tj_cont=tj_c, loss=c["loss"], peak=pk["loss"], semis=c["cond"] + c["sw"],
                                semis_pk=pk["cond"] + pk["sw"])
                    if worst is None or cand["loss"] > worst["loss"]:
                        worst = dict(cand, tj=max(tj, worst["tj"]) if worst else tj)
                if worst["tj"] > dd.TJ_LIMIT or worst["tj_cont"] > TJ_CONT_MAX:
                    continue
                m_sink = dd.sink_mass(max(2.0, worst["semis_pk"] * dd.T_PEAK / (900 * dd.DT_SINK_PEAK)), worst["semis"])
                items, n_dev = bom([(d, 4)], 0, None, m_sink, FIX_CHOP)
                rows.append(dict(f=f, sw=d.name, devices=n_dev, proto=sum(v[0] for v in items.values()),
                                 k1=sum(v[1] for v in items.values()), loss=worst["loss"], peak=worst["peak"],
                                 tj_pk=worst["tj"], tj_cont=worst["tj_cont"], items=items))
    return rows


def frontier(rows, key):
    out, best = [], float("inf")
    for r in sorted(rows, key=lambda r: r["k1"]):
        if r[key] < best - 1e-9:
            out.append(r)
            best = r[key]
    return out


def show_items(items):
    for k, (p, k1) in items.items():
        print(f"    {k:32s} ${p:7.0f}   ${k1:7.0f}")
    print(f"    {'TOTAL':32s} ${sum(v[0] for v in items.values()):7.0f}   ${sum(v[1] for v in items.values()):7.0f}")


def main():
    out = {}
    print(f"20 kW-peak blocks, {dd.I_PEAK:.0f} A peak current.  Columns: prototype quantity / 1000 units.\n")
    rows = search_isolated()
    eff = lambda r, v: 100 * (1 - r["loss"][v] / dd.P_CONT)
    print(f"=== Isolated block: cost-versus-efficiency frontier ({len(rows)} valid designs) ===")
    print("1k $  | proto $ | f kHz | xfmr recipe | HF per group        | unfolder per group  | dev | eta 85/120/240 V      | Tj cont/pk")
    fr = frontier(rows, "typ")
    for r in fr:
        print(f"{r['k1']:5.0f} | {r['proto']:6.0f}  | {r['f']/1e3:4.0f}  | {r['recipe']:11s} | {r['hf']:19s} | {r['unf']:19s} | {r['devices']:3d} | "
              f"{eff(r,'85'):.2f} / {eff(r,'120'):.2f} / {eff(r,'240'):.2f} | {r['tj_cont']:.0f} / {r['tj_pk']:.0f}")
    base = next(r for r in rows if r["recipe"] == "efficiency" and r["f"] == 70e3 and r["hf"] == "6x 16 mOhm TO-247-4"
                and r["unf"] == "6x 16 mOhm TO-247-4")
    print(f"\nPrevious 'balanced' design in this cost model: proto ${base['proto']:.0f}, 1k ${base['k1']:.0f}, "
          f"eta {eff(base,'85'):.2f} / {eff(base,'120'):.2f} / {eff(base,'240'):.2f} %")
    # Selections: cheapest design that gives up at most X points of typical efficiency vs the balanced design
    picks = {}
    for name, give in (("same efficiency", 0.0), ("-0.5 point", 50.0), ("-1 point", 100.0), ("cheapest valid", 1e9)):
        ok = [r for r in rows if r["typ"] <= base["typ"] + give]
        picks[name] = min(ok, key=lambda r: r["k1"])
    print("\n=== Isolated block: what each step of efficiency buys ===")
    for name, r in picks.items():
        print(f"  {name:16s} 1k ${r['k1']:5.0f}  proto ${r['proto']:5.0f}  {r['f']/1e3:.0f} kHz  HF {r['hf']:19s} unfolder {r['unf']:19s} "
              f"{r['devices']:3d} dev  eta {eff(r,'85'):.2f} / {eff(r,'120'):.2f} / {eff(r,'240'):.2f} %  "
              f"loss@240 {r['loss']['240']:.0f} W  pk loss {r['peak_loss']:.0f} W  Tj {r['tj_cont']:.0f}/{r['tj_pk']:.0f}")
    sel = picks["-1 point"]
    x = sel["xf"]
    print(f"\n=== Selected cost-optimised isolated block ({sel['f']/1e3:.0f} kHz) ===")
    print(f"  transformer: {x['stack']}x {x['core']}, {x['n']}:{x['n']} turns, {x['strand_mm']} mm strand, {x['mass_kg']:.2f} kg, "
          f"leakage {x['l_leak_nH']:.0f} nH, proto ${xf_cost(x)[0]:.0f} / 1k ${xf_cost(x)[1]:.0f}; heatsink {sel['m_sink']:.1f} kg")
    print("  10 kW loss by voltage: " + ", ".join(f"{v} V {l:.0f} W" for v, l in sel["loss"].items()))
    print(f"    {'':32s} {'proto':>8s}   {'1k':>8s}")
    show_items(sel["items"])
    print("  --- for comparison, the previous balanced design ---")
    show_items(base["items"])
    out["isolated"] = dict(frontier=[{k: v for k, v in r.items() if k not in ("items", "xf")} for r in fr],
                           picks={n: {k: v for k, v in r.items() if k != "xf"} for n, r in picks.items()},
                           baseline={k: v for k, v in base.items() if k != "xf"})

    crows = search_chopper()
    print(f"\n=== Non-isolated chopper (120 V <-> 277/230 V): frontier ({len(crows)} valid designs, worse of the two ratios) ===")
    print("1k $  | proto $ | f kHz | per group           | dev | 10 kW loss / eta | 20 kW loss | Tj cont/pk")
    cfr = frontier(crows, "loss")
    for r in cfr:
        print(f"{r['k1']:5.0f} | {r['proto']:6.0f}  | {r['f']/1e3:4.0f}  | {r['sw']:19s} | {r['devices']:3d} | {r['loss']:4.0f} W / {100*(1-r['loss']/dd.P_CONT):.2f} % | "
              f"{r['peak']:5.0f} W    | {r['tj_cont']:.0f} / {r['tj_pk']:.0f}")
    cbase = next(r for r in crows if r["f"] == 70e3 and r["sw"] == "5x 16 mOhm TO-247-4")
    print(f"\nPrevious chopper design in this cost model: proto ${cbase['proto']:.0f}, 1k ${cbase['k1']:.0f}, loss {cbase['loss']:.0f} W")
    csel = min((r for r in crows if r["loss"] <= cbase["loss"] + 50.0), key=lambda r: r["k1"])
    print(f"\n=== Selected cost-optimised chopper: {csel['f']/1e3:.0f} kHz, {csel['sw']} per group, {csel['devices']} devices, "
          f"{csel['loss']:.0f} W at 10 kW ({100*(1-csel['loss']/dd.P_CONT):.2f} %), Tj {csel['tj_cont']:.0f}/{csel['tj_pk']:.0f} C ===")
    print(f"    {'':32s} {'proto':>8s}   {'1k':>8s}")
    show_items(csel["items"])
    out["chopper"] = dict(frontier=cfr, selected=csel, baseline=cbase)

    print("\n=== Scaling at 1000-unit cost ===")
    for label, n in (("one block", 1), ("three-phase bank", 3), ("three-phase, 5 in parallel", 15)):
        print(f"  {label:28s} isolated ${sel['k1']*n:7.0f}   non-isolated ${csel['k1']*n:7.0f}")
    with open(os.path.join(dd.OUT, "results_cost.json"), "w") as fh:
        json.dump(out, fh, indent=1, default=lambda o: float(o) if hasattr(o, "__float__") else str(o))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 4.5))
    col = {"16": "C0", "40": "C1", "75": "C2"}
    for r in rows:
        a.plot(r["k1"], 100 * (1 - r["typ"] / dd.P_CONT), ".", ms=2, alpha=0.25, color=col[r["hf"].split("x ")[1][:2]])
    a.plot([r["k1"] for r in fr], [100 * (1 - r["typ"] / dd.P_CONT) for r in fr], "k-", lw=1.2, label="frontier")
    a.plot(base["k1"], 100 * (1 - base["typ"] / dd.P_CONT), "s", color="C3", ms=8, label="previous balanced design")
    a.plot(sel["k1"], 100 * (1 - sel["typ"] / dd.P_CONT), "*", color="C3", ms=14, label="cost-optimised selection")
    for k, c in col.items():
        a.plot([], [], ".", color=c, label=f"{k} mohm HF devices")
    a.set_xlabel("cost at 1000 units, USD")
    a.set_ylabel("efficiency at 10 kW, mean of 120 / 208 / 240 V, %")
    a.set_title("Isolated block")
    a.set_ylim(94, 99)
    a.grid(alpha=0.3)
    a.legend(fontsize=7)
    for r in crows:
        b.plot(r["k1"], 100 * (1 - r["loss"] / dd.P_CONT), ".", ms=4, alpha=0.5, color=col[r["sw"].split("x ")[1][:2]])
    b.plot([r["k1"] for r in cfr], [100 * (1 - r["loss"] / dd.P_CONT) for r in cfr], "k-", lw=1.2)
    b.plot(cbase["k1"], 100 * (1 - cbase["loss"] / dd.P_CONT), "s", color="C3", ms=8)
    b.plot(csel["k1"], 100 * (1 - csel["loss"] / dd.P_CONT), "*", color="C3", ms=14)
    b.set_xlabel("cost at 1000 units, USD")
    b.set_ylabel("efficiency at 10 kW, %")
    b.set_title("Non-isolated chopper")
    b.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(dd.OUT, "img", "cost_frontier.png"), dpi=130)


if __name__ == "__main__":
    main()
