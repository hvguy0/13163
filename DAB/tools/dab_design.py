#!/usr/bin/env python3
"""
Design model for a 1:1 isolated, bidirectional AC-AC dual-active-bridge
(AC-link DAB with line-frequency unfolders).

  85-285 Vrms in = out, 10 kW continuous, 100 kW for 10 s, fsw >= 50 kHz.

Run:  python3 dab_design.py            (prints tables, writes results.json + plots)

Everything here is first-pass analytical sizing.  Values tagged EST are
engineering estimates that must be replaced with datasheet / measured values
before hardware is committed (see docs/DESIGN.md, section "Open items").
"""
import json
import math
import os
from dataclasses import dataclass

import numpy as np

MU0 = 4e-7 * math.pi
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "docs")

# --------------------------------------------------------------------------
# Specification
# --------------------------------------------------------------------------
V_MIN, V_MAX = 85.0, 285.0           # Vrms, both ports
P_CONT, P_PEAK, T_PEAK = 10e3, 100e3, 10.0
F_LINE = 60.0
D_PK = 0.25                          # phase shift (fraction of half period) at 100 kW / 85 V
L_STRAY = 60e-9                      # EST bridge-to-transformer bus + terminations, both sides
T_DEAD = 200e-9
T_AMB = 50.0                         # deg C inside enclosure
V_GRID = [85.0, 120.0, 208.0, 240.0, 285.0]

TH = np.linspace(0, math.pi, 721)[1:-1]     # half line cycle
SIN = np.sin(TH)


def lavg(x):
    """Average of a quantity sampled over the half line cycle."""
    return float(np.mean(x))


# --------------------------------------------------------------------------
# Semiconductors (1200 V SiC half-bridge modules)
# --------------------------------------------------------------------------
@dataclass
class Module:
    name: str
    rds25: float        # ohm per switch, typ, 25 C
    tc: float           # fractional rise of Rds per K (EST)
    rth_jc: float       # K/W per switch (EST)
    qoss400: float      # C, output charge at 400 V per switch (EST)
    qg: float           # C total gate charge
    tf: float = 30e-9   # channel current fall time (EST, gate-drive dependent)
    rth_cs: float = 0.03

    def rds(self, tj):
        return self.rds25 * (1 + self.tc * (tj - 25))

    def qoss(self, v):
        return self.qoss400 * (np.maximum(v, 1.0) / 400.0) ** 0.55


# rds25 / qg from vendor data found during the study; the rest are EST.
HM3 = Module("1200V 1.33mOhm 62mm HB (CAB760M12HM3 class)", 1.33e-3, 0.0055, 0.07, 2.4e-6, 2.7e-6)
XM3 = Module("1200V 2.6mOhm HB (CAB450M12XM3 class)", 2.6e-3, 0.0055, 0.11, 1.3e-6, 1.33e-6)
V_GATE_SWING = 19.0   # -4 / +15 V


def e_off(mod, v, i):
    """Capacitively snubbed (ZVS) turn-off energy of one switch, J."""
    v = np.maximum(v, 1e-3)
    i = np.maximum(i, 1e-6)
    c = 2 * mod.qoss(v) / v                      # both devices of the leg
    tf = mod.tf
    t1 = np.minimum(np.sqrt(2 * c * v * tf / i), tf)
    e1 = i ** 2 / (2 * c * tf) * (t1 ** 3 / 3 - t1 ** 4 / (4 * tf))
    e2 = v * i * tf / 2 * (1 - t1 / tf) ** 2
    return e1 + e2


# --------------------------------------------------------------------------
# DAB operating point (unity conversion ratio, single phase shift)
# --------------------------------------------------------------------------
def l_cell_required(f, n_cells):
    """Series inductance per cell so that P_PEAK at V_MIN needs phase shift D_PK."""
    vpk = math.sqrt(2) * V_MIN
    p_inst = 2 * P_PEAK / n_cells                # crest of the 2f power pulsation
    return vpk ** 2 * 4 * D_PK * (1 - D_PK) / (8 * f * p_inst)


def op_point(v_rms, p, n_active, f, l_cell, im_pk_403=0.0):
    """Trapezoidal-current DAB at d = 1, resistive (constant D over the line cycle)."""
    vpk = math.sqrt(2) * v_rms
    x = (2 * p / n_active) / (vpk ** 2 / (8 * f * l_cell))
    if x > 1.0:
        return None
    d = (1 - math.sqrt(1 - x)) / 2
    i1c = vpk * d / (2 * f * l_cell)             # flat-top current at line crest
    i_tr = i1c * math.sqrt((1 - 2 * d / 3) / 2)  # rms over line cycle
    im_c = im_pk_403 * vpk / 403.0               # magnetising peak at this crest
    im_rms = im_c / math.sqrt(3) / math.sqrt(2)
    w_eff = 4 * f / math.sqrt(d * (1 - 2 * d / 3))   # rms(di/dt)/rms(i), rad/s
    return dict(d=d, i1c=i1c, i_tr=i_tr, im_c=im_c, im_rms=im_rms, w_eff=w_eff,
                vpk=vpk, t_phi=d / (2 * f), i_line=p / v_rms)


def cell_semi_loss(mod, o, f, tj):
    """HF-bridge losses of ONE cell (both bridges), W."""
    r = mod.rds(tj)
    i_br = math.sqrt(o["i_tr"] ** 2 + (o["im_rms"] / 2) ** 2)
    cond = 2 * 2 * r * i_br ** 2
    v = o["vpk"] * SIN
    i_sw = o["i1c"] * SIN + 0.5 * o["im_c"] * SIN
    sw_off = 8 * f * lavg(e_off(mod, v, i_sw))
    q_need = 2 * mod.qoss(v)
    resid = np.clip(1 - i_sw * T_DEAD / q_need, 0, 1)
    sw_zvs = 8 * f * lavg(resid ** 2 * mod.qoss(v) * v)
    gate = 8 * mod.qg * V_GATE_SWING * f
    return dict(cond=cond, sw=sw_off + sw_zvs, gate=gate,
                per_switch=(cond + sw_off + sw_zvs) / 8,
                zvs_frac=float(np.mean(resid < 1e-9)))


def unfolder_loss(mod, n_par, i_line, tj):
    """Both line-frequency unfolder bridges, W (two switches in series per side)."""
    r = mod.rds(tj) / n_par
    total = 2 * 2 * r * i_line ** 2
    return total, total / (8 * n_par)            # total, per switch


# --------------------------------------------------------------------------
# Ferrite
# --------------------------------------------------------------------------
# Loss anchors normalised to 100 mT, 100 C, sinusoidal [W/m^3]; beta = 2.5.
# 100 kHz and 300 kHz points are from the TDK N87 data sheet (375 kW/m^3 @ 200 mT,
# 390 kW/m^3 @ 100 mT); 25 kHz and 500 kHz points are EST.
BETA = 2.5
_FA = np.log(np.array([25e3, 100e3, 300e3, 500e3]))
_PA = np.log(np.array([10.1e3, 66.3e3, 390e3, 1216e3]))
ENV_FACTOR = lavg(SIN ** BETA)      # line-envelope average of B^beta


def _alpha(f):
    lf = math.log(f)
    k = int(np.clip(np.searchsorted(_FA, lf) - 1, 0, len(_FA) - 2))
    return (_PA[k + 1] - _PA[k]) / (_FA[k + 1] - _FA[k]), k


def pv_core(f, b_pk, mat=1.0):
    """Core loss density W/m^3 for a triangular flux (square-wave voltage), iGSE."""
    a, k = _alpha(f)
    p100 = math.exp(_PA[k] + a * (math.log(f) - _FA[k]))
    th = np.linspace(0, 2 * math.pi, 4001)
    integ = np.trapezoid(np.abs(np.cos(th)) ** a, th)
    tri = 4 ** a / ((2 * math.pi) ** (a - 1) * integ)
    return mat * tri * p100 * (b_pk / 0.1) ** BETA


@dataclass
class Core:
    name: str
    ae: float      # mm^2 (one set)
    le: float      # mm
    ve: float      # mm^3
    ww: float      # window width (radial build), mm
    hw: float      # window height (winding breadth), mm
    a: float       # centre-leg width, mm
    b: float       # centre-leg depth, mm
    w: float       # overall width, mm
    h: float       # overall height of the set, mm


# Catalogue-nominal dimensions (EST from memory of IEC/vendor tables - verify).
CORES = [
    Core("E65/32/27", 535, 147, 78650, 12.1, 44.4, 20.0, 27.4, 65.0, 65.6),
    Core("E71/33/32", 683, 149, 102000, 13.0, 43.8, 22.0, 32.0, 70.5, 66.4),
    Core("E80/38/20", 390, 184, 71800, 19.6, 56.4, 19.8, 19.8, 80.0, 76.4),
    Core("E100/60/28", 738, 274, 202000, 22.8, 93.7, 27.5, 27.5, 100.3, 119.0),
    Core("UU93/152/30", 840, 354, 297000, 34.6, 96.0, 28.0, 30.0, 93.0, 152.0),
    Core("UU126/182/20", 560, 480, 268800, 70.0, 126.0, 28.0, 20.0, 126.0, 182.0),
]

RHO20 = 1.72e-8
K_LITZ = 0.40          # copper / winding cross-section (profiled litz) EST
G_MIN = 1.0e-3         # reinforced pri-sec barrier, m
BOBBIN = 1.5e-3
MARGIN = 3.0e-3        # each end of the winding breadth
H_CONV = 22.0          # W/m^2K forced air + radiation, EST
DT_MAX = 55.0          # K steady-state rise allowed
DT_ADIABATIC_MAX = 30.0
B_SAT_LIMIT = 0.28     # T at +10 % line, leaves margin to ~0.38 T @ 100 C
W_PER_KG = 4.0         # objective: W of continuous loss traded per kg


def rho_cu(t):
    return RHO20 * (1 + 0.00393 * (t - 20))


def xf_losses(g, o, t_w):
    """Copper and core loss of one transformer at operating point o, winding temp t_w."""
    rho = rho_cu(t_w)
    rdc = rho * g["n"] * g["mlt"] / g["a_turn"]
    fr = 1 + (math.pi ** 2 * o["w_eff"] ** 2 * MU0 ** 2 * (g["n"] / g["m"]) ** 2
              * g["strands"] ** 2 * g["d_s"] ** 6) / (768 * rho ** 2 * g["bw"] ** 2)
    p_cu = 2 * rdc * fr * o["i_tr"] ** 2 + rdc * 1.3 * o["im_rms"] ** 2
    b_pk = o["vpk"] / (4 * g["f"] * g["n"] * g["ae"])
    p_fe = pv_core(g["f"], b_pk, g["mat"]) * ENV_FACTOR * g["ve"]
    return p_cu, p_fe, fr, b_pk


def design_transformer(f, l_cell, n_cells, im_pk_403, mat=1.0):
    """Exhaustive search over core / stack / turns / interleave / strand / copper build."""
    l_target = l_cell - L_STRAY
    if l_target <= 20e-9:
        return None
    # operating points one cell must survive
    cont = [op_point(v, P_CONT, 1, f, l_cell, im_pk_403) for v in V_GRID]
    peak = op_point(V_MIN, P_PEAK, n_cells, f, l_cell, im_pk_403)
    best = None
    for core in CORES:
        for stack in (1, 2, 3, 4):
            ae = core.ae * stack * 1e-6
            ve = core.ve * stack * 1e-9
            bw = core.hw * 1e-3 - 2 * MARGIN
            for n in range(1, 13):
                b_max = 1.1 * math.sqrt(2) * V_MAX / (4 * f * n * ae)
                if b_max > B_SAT_LIMIT:
                    continue
                for m in (1, 2):
                    for d_s in (0.05e-3, 0.071e-3, 0.10e-3):
                        for xf in (0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.65, 0.8, 1.0):
                            avail = core.ww * 1e-3 - BOBBIN - m * G_MIN
                            h_cu = xf * avail            # pri + sec radial copper
                            if h_cu <= 1e-3:
                                continue
                            build0 = BOBBIN + h_cu
                            mlt0 = 2 * (core.a + core.b * stack) * 1e-3
                            # leakage: solve barrier gap g for the target
                            # L = mu0 N^2 MLT/(bw m^2) (m g + h_cu/3), MLT depends on g
                            g = G_MIN
                            for _ in range(6):
                                mlt = mlt0 + math.pi * (build0 + m * g)
                                g_new = (l_target * bw * m * m / (MU0 * n * n * mlt) - h_cu / 3) / m
                                g = g_new
                            if g < G_MIN or build0 + m * g > core.ww * 1e-3:
                                continue
                            mlt = mlt0 + math.pi * (build0 + m * g)
                            a_turn = K_LITZ * (h_cu / 2) * bw / n
                            strands = a_turn / (math.pi * d_s ** 2 / 4)
                            m_cu = 2 * n * mlt * a_turn * 8960
                            m_core = ve * 4850
                            # surface for cooling
                            depth = core.b * stack * 1e-3 + 2 * (build0 + m * g)
                            surf = 2 * (core.w * core.h * 1e-6 + (core.w + core.h) * 1e-3 * depth)

                            geo = dict(n=n, m=m, mlt=mlt, a_turn=a_turn, strands=strands, d_s=d_s,
                                       bw=bw, ae=ae, ve=ve, f=f, mat=mat)

                            def losses(o, t_w, geo=geo):
                                return xf_losses(geo, o, t_w)

                            cl = [losses(o, 100.0) for o in cont]
                            p_tot = [c[0] + c[1] for c in cl]
                            dt = max(p_tot) / (H_CONV * surf)
                            if dt > DT_MAX:
                                continue
                            pk = losses(peak, 110.0)
                            dt_ad = pk[0] * T_PEAK / (m_cu * 385)
                            if dt_ad > DT_ADIABATIC_MAX:
                                continue
                            mass = m_cu + m_core
                            j = float(np.mean(p_tot)) + W_PER_KG * mass
                            if best is None or j < best["j"]:
                                best = dict(
                                    j=j, core=core.name, stack=stack, n=n, m=m,
                                    strand_mm=d_s * 1e3, strands=int(round(strands)),
                                    a_turn_mm2=a_turn * 1e6, gap_mm=g * 1e3,
                                    h_cu_mm=h_cu * 1e3, mlt_mm=mlt * 1e3,
                                    l_leak_nH=l_target * 1e9, mass_kg=mass,
                                    m_cu_kg=m_cu, m_core_kg=m_core,
                                    b_pk_285_mT=cl[-1][3] * 1e3, b_max_mT=b_max * 1e3,
                                    p_cont_W={str(int(v)): round(p, 1) for v, p in zip(V_GRID, p_tot)},
                                    p_cu_cont_W={str(int(v)): round(c[0], 1) for v, c in zip(V_GRID, cl)},
                                    p_fe_cont_W={str(int(v)): round(c[1], 1) for v, c in zip(V_GRID, cl)},
                                    fr_cont_85=cl[0][2], fr_peak=pk[2],
                                    dt_cont_K=dt, p_cu_peak_W=pk[0], p_fe_peak_W=pk[1],
                                    dt_adiabatic_K=dt_ad, surf_m2=surf,
                                    lm_uH=(403.0 / (4 * f * im_pk_403) * 1e6) if im_pk_403 else None,
                                    _geo=geo)
    return best


# --------------------------------------------------------------------------
# System evaluation
# --------------------------------------------------------------------------
R_BUS_SIDE = 0.15e-3     # EST busbars + EMI filter copper per port, ohm
P_AUX = 35.0             # control, sensing, fans


def system_point(v, p, n_active, f, l_cell, n_cells, mod, unf_mod, unf_par, xf, im, tj):
    o = op_point(v, p, n_active, f, l_cell, im)
    if o is None:
        return None
    s = cell_semi_loss(mod, o, f, tj)
    p_cu, p_fe, _, _ = xf_losses(xf["_geo"], o, 100.0)
    unf, unf_sw = unfolder_loss(unf_mod, unf_par, o["i_line"], tj)
    bus = 2 * R_BUS_SIDE * o["i_line"] ** 2
    gate = s["gate"] * n_active
    loss = n_active * (s["cond"] + s["sw"] + p_cu + p_fe) + gate + unf + bus + P_AUX
    return dict(v=v, p=p, n_active=n_active, d=o["d"], t_phi_ns=o["t_phi"] * 1e9,
                i_line=o["i_line"], i_tr=o["i_tr"], i1c=o["i1c"],
                hf_cond=n_active * s["cond"], hf_sw=n_active * s["sw"], gate=gate,
                xf_cu=n_active * p_cu, xf_fe=n_active * p_fe, unf=unf, bus=bus, aux=P_AUX,
                loss=loss, eff=1 - loss / p, hf_per_switch=s["per_switch"],
                unf_per_switch=unf_sw, zvs_frac=s["zvs_frac"])


def best_cont(v, p, **kw):
    """Pick the number of active cells that minimises loss (cell shedding)."""
    cands = [system_point(v, p, na, tj=80.0, **kw) for na in range(1, kw["n_cells"] + 1)]
    cands = [c for c in cands if c]
    return min(cands, key=lambda c: c["loss"])


M_HEATSINK = 14.0   # kg aluminium in the semiconductor heatsink (EST)
T_SINK_CONT = 65.0


def peak_point(v, **kw):
    """100 kW for 10 s: iterate junction temperature."""
    tj = 120.0
    for _ in range(4):
        r = system_point(v, P_PEAK, kw["n_cells"], tj=tj, **kw)
        if r is None:
            return None
        semis = r["hf_cond"] + r["hf_sw"] + r["unf"]
        dts = semis * T_PEAK / (M_HEATSINK * 900)
        tj_hf = T_SINK_CONT + dts + r["hf_per_switch"] * (kw["mod"].rth_jc + kw["mod"].rth_cs)
        tj_unf = T_SINK_CONT + dts + r["unf_per_switch"] * (kw["unf_mod"].rth_jc + kw["unf_mod"].rth_cs)
        tj = max(tj_hf, tj_unf)
    r.update(tj_hf=tj_hf, tj_unf=tj_unf, dt_sink=dts)
    return r


def evaluate(f, n_cells, mod=HM3, unf_mod=HM3, unf_par=2, mat=1.0):
    l_cell = l_cell_required(f, n_cells)
    im = 4 * float(mod.qoss(403.0)) / T_DEAD        # magnetising peak for ZVS at crest
    xf = design_transformer(f, l_cell, n_cells, im, mat)
    if xf is None:
        return dict(f=f, n_cells=n_cells, l_cell_nH=l_cell * 1e9, feasible=False)
    kw = dict(f=f, l_cell=l_cell, n_cells=n_cells, mod=mod, unf_mod=unf_mod,
              unf_par=unf_par, xf=xf, im=im)
    cont = {str(int(v)): best_cont(v, P_CONT, **kw) for v in V_GRID}
    part = {str(int(v)): best_cont(v, 0.25 * P_CONT, **kw) for v in V_GRID}
    peak = {str(int(v)): peak_point(v, **kw) for v in V_GRID}
    res = dict(f=f, n_cells=n_cells, module=mod.name, feasible=True,
               l_cell_nH=l_cell * 1e9, im_pk_A=im,
               xf={k: v for k, v in xf.items() if not k.startswith("_")},
               cont=cont, part=part, peak=peak)
    res["_kw"] = kw
    return res


def fmt_row(cols, widths):
    return " | ".join(str(c).ljust(w) for c, w in zip(cols, widths))


def main():
    out = {}
    print("\n=== Cell-count / module study at 50 kHz (peak corner 100 kW @ 85 V) ===")
    w = [34, 3, 9, 10, 10, 10, 8, 8, 8]
    print(fmt_row(["module", "N", "L/cell nH", "HF mods", "loss85 kW", "loss240 kW", "Tj_hf", "Tj_unf", "xf kg"], w))
    study = []
    for mod, ns in ((HM3, (3, 4, 5, 6)), (XM3, (6, 8, 10))):
        for n in ns:
            r = evaluate(50e3, n, mod)
            if not r["feasible"]:
                print(fmt_row([mod.name[:34], n, f"{r['l_cell_nH']:.0f}", "-", "infeasible"], w))
                continue
            p85, p240 = r["peak"]["85"], r["peak"]["240"]
            row = dict(module=mod.name, n=n, l_cell_nH=r["l_cell_nH"], hf_modules=4 * n,
                       loss85_kW=p85["loss"] / 1e3, loss240_kW=p240["loss"] / 1e3,
                       tj_hf=p85["tj_hf"], tj_unf=p85["tj_unf"], xf_mass_total=n * r["xf"]["mass_kg"],
                       eff10k_240=r["cont"]["240"]["eff"])
            study.append(row)
            print(fmt_row([mod.name[:34], n, f"{row['l_cell_nH']:.0f}", 4 * n, f"{row['loss85_kW']:.2f}",
                           f"{row['loss240_kW']:.2f}", f"{row['tj_hf']:.0f}", f"{row['tj_unf']:.0f}",
                           f"{row['xf_mass_total']:.1f}"], w))
    out["cell_study"] = study

    print("\n=== Frequency evaluation (N = 4 cells, HM3-class modules) ===")
    freqs = [50e3, 70e3, 100e3, 140e3, 200e3, 300e3]
    w = [6, 8, 22, 4, 7, 7, 9, 9, 9, 9, 9, 8]
    print(fmt_row(["f kHz", "L nH", "core", "N", "gap mm", "xf kg", "xf W@240", "eta10@240",
                   "eta10@85", "pk85 kW", "Tj pk", "tphi ns"], w))
    sweep = []
    for f in freqs:
        mat = 1.0 if f < 250e3 else 0.45      # EST: HF grade (N49/3F36 class) above 250 kHz
        r = evaluate(f, 4, HM3, mat=mat)
        if not r["feasible"]:
            print(fmt_row([f"{f/1e3:.0f}", f"{r['l_cell_nH']:.0f}", "no transformer meets leakage/thermal"], w))
            sweep.append(dict(f=f, feasible=False, l_cell_nH=r["l_cell_nH"]))
            continue
        x = r["xf"]
        c240, c85, p85 = r["cont"]["240"], r["cont"]["85"], r["peak"]["85"]
        print(fmt_row([f"{f/1e3:.0f}", f"{r['l_cell_nH']:.0f}", f"{x['stack']}x {x['core']}", x["n"],
                       f"{x['gap_mm']:.1f}", f"{x['mass_kg']:.2f}", f"{x['p_cont_W']['240']:.0f}",
                       f"{c240['eff']*100:.2f}", f"{c85['eff']*100:.2f}", f"{p85['loss']/1e3:.2f}",
                       f"{max(p85['tj_hf'], p85['tj_unf']):.0f}", f"{c240['t_phi_ns']:.0f}"], w))
        sweep.append({k: v for k, v in r.items() if not k.startswith("_")})
    out["freq_sweep"] = sweep

    # ---- selected design: detailed tables ----
    f_sel, n_sel = 70e3, 4
    r = evaluate(f_sel, n_sel, HM3)
    out["selected"] = {k: v for k, v in r.items() if not k.startswith("_")}
    x = r["xf"]
    print(f"\n=== Selected design: {f_sel/1e3:.0f} kHz, {n_sel} cells ===")
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in x.items()
                      if not k.startswith("_")}, indent=1))
    w = [6, 7, 6, 8, 8, 8, 8, 8, 8, 8, 8, 9, 8]
    for label, key in (("10 kW continuous", "cont"), ("2.5 kW", "part"), ("100 kW / 10 s", "peak")):
        print(f"\n-- {label} --")
        print(fmt_row(["Vrms", "cells", "D", "tphi ns", "Itr/cell", "HF cond", "HF sw", "gate",
                       "xf cu", "xf fe", "unfold", "loss W", "eta %"], w))
        for v in V_GRID:
            c = r[key][str(int(v))]
            print(fmt_row([int(v), c["n_active"], f"{c['d']:.4f}", f"{c['t_phi_ns']:.0f}", f"{c['i_tr']:.0f}",
                           f"{c['hf_cond']:.0f}", f"{c['hf_sw']:.0f}", f"{c['gate']:.0f}", f"{c['xf_cu']:.0f}",
                           f"{c['xf_fe']:.0f}", f"{c['unf']:.0f}", f"{c['loss']:.0f}", f"{c['eff']*100:.2f}"], w))
            if key == "peak":
                print(f"       Tj HF {c['tj_hf']:.0f} C, Tj unfolder {c['tj_unf']:.0f} C, "
                      f"sink +{c['dt_sink']:.1f} K, ZVS over {c['zvs_frac']*100:.0f}% of line cycle")

    with open(os.path.join(OUT, "results.json"), "w") as fh:
        json.dump(out, fh, indent=1, default=float)
    make_plots(out, r)


def make_plots(out, sel):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sw = [s for s in out["freq_sweep"] if s.get("feasible")]
    fk = [s["f"] / 1e3 for s in sw]
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
    keys = [("xf_fe", "transformer core"), ("xf_cu", "transformer copper"), ("hf_cond", "HF bridge conduction"),
            ("hf_sw", "HF bridge switching"), ("gate", "gate drive"), ("unf", "unfolders"), ("bus", "bus + filter"),
            ("aux", "aux")]
    for a, vkey, title in ((ax[0], "240", "Loss at 10 kW, 240 V"), (ax[1], "85", "Loss at 10 kW, 85 V")):
        bottom = np.zeros(len(sw))
        for k, lab in keys:
            vals = np.array([s["cont"][vkey][k] for s in sw])
            a.bar(range(len(sw)), vals, bottom=bottom, label=lab)
            bottom += vals
        a.set_xticks(range(len(sw)), [f"{x:.0f}" for x in fk])
        a.set_xlabel("switching frequency, kHz")
        a.set_ylabel("W")
        a.set_title(title)
        a.grid(axis="y", alpha=0.3)
    ax[0].legend(fontsize=7)
    ax2 = ax[2]
    ax2.plot(fk, [4 * s["xf"]["mass_kg"] for s in sw], "o-", label="transformer mass, 4 cells (kg)")
    ax2.plot(fk, [s["peak"]["85"]["loss"] / 1e3 for s in sw], "s-", label="loss at 100 kW / 85 V (kW)")
    ax2.plot(fk, [s["cont"]["240"]["t_phi_ns"] / 10 for s in sw], "^-", label="phase shift at 10 kW / 240 V (x10 ns)")
    ax2.set_xlabel("switching frequency, kHz")
    ax2.set_title("Mass, peak loss, timing")
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "img", "frequency_sweep.png"), dpi=130)

    # efficiency vs power for the selected design
    kw = sel["_kw"]
    fig, a = plt.subplots(figsize=(7.5, 4.5))
    ps = np.logspace(math.log10(500), 5, 60)
    for v in V_GRID:
        eff = []
        for p in ps:
            if p <= P_CONT:
                c = best_cont(v, p, **kw)
            else:
                c = system_point(v, p, kw["n_cells"], tj=110.0, **kw)
            eff.append(c["eff"] * 100 if c else np.nan)
        a.semilogx(ps / 1e3, eff, label=f"{v:.0f} V")
    a.axvline(10, color="k", ls=":", lw=0.8)
    a.set_ylim(85, 100)
    a.set_xlabel("power, kW (above 10 kW: 10 s rating)")
    a.set_ylabel("efficiency, %")
    a.set_title(f"Predicted efficiency, {kw['f']/1e3:.0f} kHz, {kw['n_cells']} cells with cell shedding")
    a.grid(alpha=0.3, which="both")
    a.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "img", "efficiency.png"), dpi=130)


if __name__ == "__main__":
    main()
