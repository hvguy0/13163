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
# Rev B peak envelope: 100 kW down to V_KNEE, constant current below it.
V_KNEE = 200.0
I_PEAK = P_PEAK / V_KNEE             # 500 A rms
V_D = 120.0                          # lowest voltage at which I_PEAK is delivered with D = D_PK
F_LINE = 60.0
D_PK = 0.25                          # phase shift (fraction of half period) at I_PEAK / V_D
D_MAX = 0.35                         # never run beyond this
L_STRAY = 60e-9                      # EST bridge-to-transformer bus + terminations, both sides
T_DEAD = 200e-9
T_AMB = 50.0                         # deg C inside enclosure
TJ_LIMIT = 125.0                     # design target at the end of the 10 s peak: 25 K under the 150 C ceiling used for EST thermal data (175 C rated)
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
    cost_sw: float      # USD per switch position, low volume (EST)
    rth_cs: float = 0.03
    tf: float = 30e-9   # channel current fall time (EST, gate-drive dependent)
    n_par: int = 1

    def rds(self, tj):
        return self.rds25 * (1 + self.tc * (tj - 25))

    def qoss(self, v):
        return self.qoss400 * (np.maximum(v, 1.0) / 400.0) ** 0.55

    def par(self, m):
        """m devices in parallel per switch position."""
        return Module(f"{m}x {self.name}", self.rds25 / m, self.tc, self.rth_jc / m, self.qoss400 * m,
                      self.qg * m, self.cost_sw * m, self.rth_cs / m, self.tf, m)


# rds25 / qg of the two modules are from vendor listings; everything else,
# including every price, is EST.
HM3 = Module("1.33 mOhm 62 mm half-bridge module", 1.33e-3, 0.0055, 0.07, 2.4e-6, 2.7e-6, 950.0)
XM3 = Module("2.6 mOhm half-bridge module", 2.6e-3, 0.0055, 0.11, 1.3e-6, 1.33e-6, 425.0)
DISC = Module("16 mOhm TO-247-4 discrete", 16e-3, 0.0055, 0.27, 0.20e-6, 0.21e-6, 38.0, rth_cs=0.45)
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
    """Series inductance per cell so that I_PEAK at V_D needs phase shift D_PK."""
    vpk = math.sqrt(2) * V_D
    p_inst = 2 * V_D * I_PEAK / n_cells          # crest of the 2f power pulsation
    return vpk ** 2 * 4 * D_PK * (1 - D_PK) / (8 * f * p_inst)


def p_peak_at(v, f, l_cell, n_cells):
    """10 s power available at v: 100 kW, the current limit, or the D_MAX limit."""
    cap = n_cells * (math.sqrt(2) * v) ** 2 * 4 * D_MAX * (1 - D_MAX) / (8 * f * l_cell) / 2
    return min(P_PEAK, v * I_PEAK, cap)


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
    peak = op_point(V_D, V_D * I_PEAK, n_cells, f, l_cell, im_pk_403)
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
                                    box_L=core.w * core.h * depth * 1e-3,
                                    lm_uH=(403.0 / (4 * f * im_pk_403) * 1e6) if im_pk_403 else None,
                                    _geo=geo)
    return best


# --------------------------------------------------------------------------
# System evaluation
# --------------------------------------------------------------------------
R_BUS_SIDE = 0.15e-3     # EST busbars + EMI filter copper per port, ohm
P_AUX = 35.0             # control, sensing, fans
T_SINK_CONT = 65.0       # heatsink temperature before the peak
DT_SINK_PEAK = 15.0      # heatsink mass is chosen to give this rise in the 10 s event


def system_point(v, p, n_active, f, l_cell, n_cells, mod, unf_mod, xf, im, tj, tj_unf=None):
    o = op_point(v, p, n_active, f, l_cell, im)
    if o is None or o["d"] > D_MAX + 1e-9:
        return None
    s = cell_semi_loss(mod, o, f, tj)
    p_cu, p_fe, _, _ = xf_losses(xf["_geo"], o, 100.0)
    unf, unf_sw = unfolder_loss(unf_mod, 1, o["i_line"], tj if tj_unf is None else tj_unf)
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


def peak_point(v, **kw):
    """10 s peak at v: junction temperatures at the END of the event, self-consistent with Rds(T)."""
    p = p_peak_at(v, kw["f"], kw["l_cell"], kw["n_cells"])
    tj_hf = tj_unf = 120.0
    r = None
    for _ in range(12):
        r = system_point(v, p, kw["n_cells"], tj=tj_hf, tj_unf=tj_unf, **kw)
        if r is None:
            return None
        base = T_SINK_CONT + DT_SINK_PEAK
        tj_hf = min(base + r["hf_per_switch"] * (kw["mod"].rth_jc + kw["mod"].rth_cs), 400.0)
        tj_unf = min(base + r["unf_per_switch"] * (kw["unf_mod"].rth_jc + kw["unf_mod"].rth_cs), 400.0)
    r.update(tj_hf=tj_hf, tj_unf=tj_unf, e_semis=(r["hf_cond"] + r["hf_sw"] + r["unf"]) * T_PEAK)
    return r


_XF_CACHE = {}


def evaluate(f, n_cells, mod, unf_mod, mat=1.0):
    l_cell = l_cell_required(f, n_cells)
    im = 4 * float(mod.qoss(403.0)) / T_DEAD        # magnetising peak for ZVS at crest
    key = (f, n_cells, round(im), mat)
    if key not in _XF_CACHE:
        _XF_CACHE[key] = design_transformer(f, l_cell, n_cells, im, mat)
    xf = _XF_CACHE[key]
    if xf is None:
        return dict(f=f, n_cells=n_cells, l_cell_nH=l_cell * 1e9, feasible=False)
    kw = dict(f=f, l_cell=l_cell, n_cells=n_cells, mod=mod, unf_mod=unf_mod, xf=xf, im=im)
    cont = {str(int(v)): best_cont(v, P_CONT, **kw) for v in V_GRID}
    part = {str(int(v)): best_cont(v, 0.25 * P_CONT, **kw) for v in V_GRID}
    peak = {str(int(v)): peak_point(v, **kw) for v in V_GRID}
    tj_hf = max(p["tj_hf"] for p in peak.values())
    tj_unf = max(p["tj_unf"] for p in peak.values())
    e_max = max(p["e_semis"] for p in peak.values())
    res = dict(f=f, n_cells=n_cells, hf=mod.name, unfolder=unf_mod.name, feasible=True,
               l_cell_nH=l_cell * 1e9, im_pk_A=im, tj_hf=tj_hf, tj_unf=tj_unf,
               m_sink_kg=max(3.0, e_max / (900 * DT_SINK_PEAK)),
               xf={k: v for k, v in xf.items() if not k.startswith("_")},
               cont=cont, part=part, peak=peak)
    res["_kw"] = kw
    return res


# --------------------------------------------------------------------------
# Cost / volume / mass roll-up.  Every figure here is a rough EST for comparing
# options against each other, not a quotation.
# --------------------------------------------------------------------------
def pkg_volume_l(mod, positions):
    if "62 mm" in mod.name:
        return 0.20 * positions / 2 * mod.n_par + 0.04 * positions
    if "module" in mod.name:
        return 0.10 * positions / 2 * mod.n_par + 0.04 * positions
    return 0.012 * positions * mod.n_par + 0.02 * positions


def rollup(res, c_link_uF=40.0):
    kw = res["_kw"]
    n, hf, unf, xf = kw["n_cells"], kw["mod"], kw["unf_mod"], kw["xf"]
    m_sink = res["m_sink_kg"]
    items = {  # name: (cost USD, volume L, mass kg)
        "HF bridge switches": (8 * n * hf.cost_sw, pkg_volume_l(hf, 8 * n), 0.3 * n),
        "Unfolder switches": (8 * unf.cost_sw, pkg_volume_l(unf, 8), 0.3),
        "Gate drives": (30 * 8 * n + 15 * 8, 0.0, 0.3),
        "Transformers": (450 * n, 1.3 * xf["box_L"] * n, xf["mass_kg"] * n),
        "Link capacitors": (0.7 * 2 * c_link_uF, 0.004 * 2 * c_link_uF, 0.004 * 2 * c_link_uF),
        "Heatsink and fans": (12 * m_sink + 80, m_sink / 2.7 / 0.35 + 1.0, m_sink + 0.5),
        "EMI filters (2 ports)": (700, 4.0, 6.0),
        "Contactors, fuses, surge (2 ports)": (500, 1.6, 2.4),
        "Sensing, control, aux supply": (550, 1.2, 0.8),
        "Busbars, PCBs, enclosure": (700, 0.0, 4.0),
    }
    return finish(items)


def finish(items, packing=0.45):
    cost = sum(v[0] for v in items.values())
    vol = sum(v[1] for v in items.values()) / packing
    mass = sum(v[2] for v in items.values())
    return dict(items={k: [round(x, 2) for x in v] for k, v in items.items()},
                cost=cost, volume_L=vol, mass_kg=mass)


def non_isolated():
    """
    Transformerless alternative, kept deliberately simple: one bidirectional SiC
    AC switch (two common-source positions, always conducting) in series with
    the line, with a snubber / surge absorber across it.  It connects at a
    voltage zero, carries the 500 A surge for 10 s, and opens in microseconds on
    over-current, over-temperature or command.  No PWM, no magnetics.
    Sensing, controller and telemetry are the same as the isolated block.
    """
    best = None
    for m in range(2, 20):
        d = DISC.par(m)
        tj = 120.0
        for _ in range(12):
            p_sw = d.rds(tj) * I_PEAK ** 2           # conducts the full cycle
            tj = min(T_SINK_CONT + DT_SINK_PEAK + p_sw * (d.rth_jc + d.rth_cs), 400.0)
        if tj <= TJ_LIMIT:
            best = (m, d, tj, p_sw)
            break
    m, d, tj, p_sw = best
    m_sink = max(2.0, 2 * p_sw * T_PEAK / (900 * DT_SINK_PEAK))
    loss = {}
    for v in V_GRID:
        i = P_CONT / v
        loss[str(int(v))] = 2 * d.rds(70.0) * i ** 2 + 2 * R_BUS_SIDE * i ** 2 + 25
    items = {
        "Series AC switch": (2 * d.cost_sw, pkg_volume_l(d, 2), 0.2),
        "Gate drive": (60, 0.0, 0.1),
        "Snubber and surge absorber": (120, 0.4, 0.5),
        "Heatsink and fans": (12 * m_sink + 60, m_sink / 2.7 / 0.35 + 0.6, m_sink + 0.4),
        "EMI filters (2 ports, smaller)": (300, 1.6, 2.4),
        "Contactors, fuses, surge (2 ports)": (500, 1.6, 2.4),
        "Sensing, control, aux supply": (550, 1.2, 0.8),
        "Busbars, PCBs, enclosure": (400, 0.0, 2.5),
    }
    r = finish(items)
    r.update(m_series=m, tj=tj, loss_10kW=loss, peak_loss=2 * p_sw + 2 * R_BUS_SIDE * I_PEAK ** 2,
             devices=2 * m)
    return r


def fmt_row(cols, widths):
    return " | ".join(str(c).ljust(w) for c, w in zip(cols, widths))


def cheapest_unfolder():
    """Unfolder choice depends only on line current, so pick it once."""
    opts = [DISC.par(m) for m in range(3, 16)] + [XM3, XM3.par(2), HM3]
    rows = []
    for u in opts:
        tj = 120.0
        for _ in range(12):
            p_sw = u.rds(tj) * I_PEAK ** 2 / 2
            tj = min(T_SINK_CONT + DT_SINK_PEAK + p_sw * (u.rth_jc + u.rth_cs), 400.0)
        rows.append((u, tj, 8 * u.cost_sw, 8 * p_sw))
    ok = [r for r in rows if r[1] <= TJ_LIMIT]
    return min(ok, key=lambda r: r[2]), rows


F_SEL = 70e3


def main():
    out = {"spec": dict(v_min=V_MIN, v_max=V_MAX, p_cont=P_CONT, p_peak=P_PEAK, i_peak=I_PEAK,
                        v_knee=V_KNEE, tj_limit=TJ_LIMIT)}
    print(f"Peak envelope: {P_PEAK/1e3:.0f} kW down to {V_KNEE:.0f} V, {I_PEAK:.0f} A below; Tj limit {TJ_LIMIT:.0f} C")

    (unf, unf_tj, unf_cost, unf_loss), rows = cheapest_unfolder()
    print("\n=== Unfolder options (per-switch thermal check at 500 A, 10 s) ===")
    for u, tj, c, pl in rows:
        if u.n_par in (4, 6, 8, 10, 12) or "module" in u.name:
            print(f"  {u.name:40s} Tj {tj:5.0f} C   cost ${c:6.0f}   loss both ports {pl*2/1e3:5.2f} kW"
                  + ("   <- cheapest that passes" if u is unf else ""))
    out["unfolder"] = dict(name=unf.name, tj=unf_tj, cost=unf_cost)

    print("\n=== HF bridge options, 70 kHz (thermally sized) ===")
    w = [5, 40, 9, 7, 9, 10, 10, 9]
    print(fmt_row(["cells", "HF switch position", "L/cell nH", "Tj C", "semis $", "eta10@240", "pk loss kW", "block $"], w))
    study, best = [], None
    for n in (1, 2, 3):
        for hf in [HM3, XM3, XM3.par(2)] + [DISC.par(m) for m in range(2, 11)]:
            r = evaluate(F_SEL, n, hf, unf)
            if not r["feasible"]:
                continue
            ok = r["tj_hf"] <= TJ_LIMIT
            ru = rollup(r)
            pk = max(p["loss"] for p in r["peak"].values())
            row = dict(n=n, hf=hf.name, l_cell_nH=r["l_cell_nH"], tj_hf=r["tj_hf"], ok=ok,
                       hf_cost=8 * n * hf.cost_sw, eff10_240=r["cont"]["240"]["eff"],
                       peak_loss_kW=pk / 1e3, block_cost=ru["cost"])
            study.append(row)
            if ok and (best is None or ru["cost"] < best[1]["cost"]):
                best = (r, ru)
            if ok or hf.n_par == 1:
                print(fmt_row([n, hf.name, f"{r['l_cell_nH']:.0f}", f"{r['tj_hf']:.0f}" + ("" if ok else " X"),
                               f"{row['hf_cost']:.0f}", f"{row['eff10_240']*100:.2f}", f"{pk/1e3:.2f}",
                               f"{ru['cost']:.0f}"], w))
    out["hf_study"] = study

    # Selection: two cells (shedding, interleaving, a workable leakage target) at lowest cost.
    cands = [(r, ru) for r, ru in ((evaluate(F_SEL, 2, DISC.par(m), unf), None) for m in range(2, 11))
             if r["feasible"] and r["tj_hf"] <= TJ_LIMIT]
    sel = cands[0][0]
    sel_ru = rollup(sel)
    print(f"\nCheapest overall: {best[0]['n_cells']} cell(s), {best[0]['hf']}, ${best[1]['cost']:.0f}")
    print(f"Selected: 2 cells, {sel['hf']}, ${sel_ru['cost']:.0f}")

    print("\n=== Frequency evaluation for the selected hardware ===")
    w = [6, 8, 22, 4, 7, 7, 9, 9, 10, 8, 8]
    print(fmt_row(["f kHz", "L nH", "core", "N", "gap mm", "xf kg", "eta10@240", "eta10@85", "pk loss kW", "Tj pk", "tphi ns"], w))
    sweep = []
    for f in [50e3, 70e3, 100e3, 140e3, 200e3, 300e3]:
        mat = 1.0 if f < 250e3 else 0.45      # EST: HF grade (N49/3F36 class) above 250 kHz
        r = evaluate(f, 2, sel["_kw"]["mod"], unf, mat=mat)
        if not r["feasible"]:
            print(fmt_row([f"{f/1e3:.0f}", f"{r['l_cell_nH']:.0f}", "no transformer meets leakage/thermal"], w))
            sweep.append(dict(f=f, feasible=False, l_cell_nH=r["l_cell_nH"]))
            continue
        x = r["xf"]
        pk = max(p["loss"] for p in r["peak"].values())
        print(fmt_row([f"{f/1e3:.0f}", f"{r['l_cell_nH']:.0f}", f"{x['stack']}x {x['core']}", x["n"],
                       f"{x['gap_mm']:.1f}", f"{x['mass_kg']:.2f}", f"{r['cont']['240']['eff']*100:.2f}",
                       f"{r['cont']['85']['eff']*100:.2f}", f"{pk/1e3:.2f}",
                       f"{max(r['tj_hf'], r['tj_unf']):.0f}", f"{r['cont']['240']['t_phi_ns']:.0f}"], w))
        d = {k: v for k, v in r.items() if not k.startswith("_")}
        d["peak_loss"] = pk
        sweep.append(d)
    out["freq_sweep"] = sweep

    r = sel
    x = r["xf"]
    out["selected"] = {k: v for k, v in r.items() if not k.startswith("_")}
    print(f"\n=== Selected design detail: {F_SEL/1e3:.0f} kHz, 2 cells, HF {r['hf']}, unfolder {r['unfolder']} ===")
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in x.items()}, indent=1))
    w = [6, 7, 6, 8, 8, 8, 8, 8, 8, 8, 8, 9, 8]
    for label, key in (("10 kW continuous", "cont"), ("2.5 kW", "part"), ("10 s peak", "peak")):
        print(f"\n-- {label} --")
        print(fmt_row(["Vrms", "cells", "D", "P kW", "Itr/cell", "HF cond", "HF sw", "gate",
                       "xf cu", "xf fe", "unfold", "loss W", "eta %"], w))
        for v in V_GRID:
            c = r[key][str(int(v))]
            print(fmt_row([int(v), c["n_active"], f"{c['d']:.4f}", f"{c['p']/1e3:.1f}", f"{c['i_tr']:.0f}",
                           f"{c['hf_cond']:.0f}", f"{c['hf_sw']:.0f}", f"{c['gate']:.0f}", f"{c['xf_cu']:.0f}",
                           f"{c['xf_fe']:.0f}", f"{c['unf']:.0f}", f"{c['loss']:.0f}", f"{c['eff']*100:.2f}"], w))
            if key == "peak":
                print(f"       Tj HF {c['tj_hf']:.0f} C, Tj unfolder {c['tj_unf']:.0f} C, ZVS {c['zvs_frac']*100:.0f}% of cycle")

    print(f"\n=== Roll-up, isolated block (heatsink {r['m_sink_kg']:.1f} kg) ===")
    for k, v in sel_ru["items"].items():
        print(f"  {k:38s} ${v[0]:7.0f}  {v[1]:5.1f} L  {v[2]:5.1f} kg")
    print(f"  TOTAL  ${sel_ru['cost']:.0f}   {sel_ru['volume_L']:.1f} L enclosure   {sel_ru['mass_kg']:.1f} kg")
    ni = non_isolated()
    print(f"\n=== Roll-up, non-isolated block ({ni['m_series']}x 16 mOhm per series position, Tj {ni['tj']:.0f} C) ===")
    for k, v in ni["items"].items():
        print(f"  {k:38s} ${v[0]:7.0f}  {v[1]:5.1f} L  {v[2]:5.1f} kg")
    print(f"  TOTAL  ${ni['cost']:.0f}   {ni['volume_L']:.1f} L enclosure   {ni['mass_kg']:.1f} kg")
    print("  loss at 10 kW:", {k: round(v) for k, v in ni["loss_10kW"].items()}, f"peak loss {ni['peak_loss']/1e3:.2f} kW")
    out["rollup_isolated"] = sel_ru
    out["rollup_non_isolated"] = ni

    print("\n=== Scaling (frame adds 15 % volume, 8 % mass per multi-block assembly) ===")
    scale = []
    for label, blocks, par in (("1-phase block", 1, 1), ("3-phase bank", 3, 1), ("3-phase, 5 in parallel", 15, 5)):
        k_v, k_m = (1.0, 1.0) if blocks == 1 else (1.15, 1.08)
        row = dict(config=label, blocks=blocks, cont_kW=P_CONT * blocks / 1e3, peak_kW=P_PEAK * blocks / 1e3,
                   iso_L=sel_ru["volume_L"] * blocks * k_v, iso_kg=sel_ru["mass_kg"] * blocks * k_m,
                   iso_cost=sel_ru["cost"] * blocks, ni_L=ni["volume_L"] * blocks * k_v,
                   ni_kg=ni["mass_kg"] * blocks * k_m, ni_cost=ni["cost"] * blocks,
                   cap_A_240=2 * math.pi * F_LINE * 40e-6 * 240 * par)
        scale.append(row)
        print(f"  {label:24s} {row['cont_kW']:5.0f} kW cont {row['peak_kW']:6.0f} kW peak | isolated {row['iso_L']:6.0f} L "
              f"{row['iso_kg']:5.0f} kg ${row['iso_cost']:7.0f} | non-isolated {row['ni_L']:5.0f} L {row['ni_kg']:4.0f} kg ${row['ni_cost']:6.0f}")
    out["scaling"] = scale

    with open(os.path.join(OUT, "results.json"), "w") as fh:
        json.dump(out, fh, indent=1, default=lambda o: float(o) if isinstance(o, (np.floating, float)) else str(o))
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
    ax2.plot(fk, [2 * s["xf"]["mass_kg"] for s in sw], "o-", label="transformer mass, 2 cells (kg)")
    ax2.plot(fk, [s["peak_loss"] / 1e3 for s in sw], "s-", label="worst 10 s peak loss (kW)")
    ax2.plot(fk, [s["cont"]["240"]["t_phi_ns"] / 10 for s in sw], "^-", label="phase shift at 10 kW / 240 V (x10 ns)")
    ax2.set_xlabel("switching frequency, kHz")
    ax2.set_title("Mass, peak loss, timing")
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "img", "frequency_sweep.png"), dpi=130)

    kw = sel["_kw"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 4.5))
    for v in V_GRID:
        pmax = p_peak_at(v, kw["f"], kw["l_cell"], kw["n_cells"])
        ps = np.logspace(math.log10(500), math.log10(pmax), 60)
        eff = []
        for p in ps:
            c = best_cont(v, p, **kw) if p <= P_CONT else system_point(v, p, kw["n_cells"], tj=110.0, **kw)
            eff.append(c["eff"] * 100 if c else np.nan)
        a.semilogx(ps / 1e3, eff, label=f"{v:.0f} V")
    a.axvline(10, color="k", ls=":", lw=0.8)
    a.set_ylim(90, 100)
    a.set_xlabel("power, kW (above 10 kW: 10 s rating)")
    a.set_ylabel("efficiency, %")
    a.set_title("Predicted efficiency, isolated block")
    a.grid(alpha=0.3, which="both")
    a.legend()
    vs = np.linspace(V_MIN, V_MAX, 100)
    b.plot(vs, [p_peak_at(v, kw["f"], kw["l_cell"], kw["n_cells"]) / 1e3 for v in vs], lw=2, label="10 s peak")
    b.axhline(10, color="C1", lw=2, label="continuous")
    b.set_xlabel("port voltage, Vrms")
    b.set_ylabel("kW")
    b.set_title("Power envelope")
    b.grid(alpha=0.3)
    b.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "img", "efficiency.png"), dpi=130)


if __name__ == "__main__":
    main()
