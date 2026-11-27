#!/usr/bin/env python3
"""
Draws the power-stage schematic of the non-isolated block (bidirectional AC
chopper, 120 V <-> 277/230 V, cost-optimised 20 kW-peak version).

Run:  pip install schemdraw matplotlib && python3 draw_noniso_schematic.py
Writes docs/img/schematic_noniso.png and .svg
"""
import os

import schemdraw
import schemdraw.elements as elm
from schemdraw import flow

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "img")
YT, YN = 8.0, 0.0          # line rail, neutral rail


def body_diode(d, fet, horizontal, ofs):
    """Anti-parallel body diode drawn beside a FET (anode at source, cathode at drain)."""
    s, dr = fet.source, fet.drain
    if horizontal:
        a, b = (s[0], s[1] + ofs), (dr[0], dr[1] + ofs)
    else:
        a, b = (s[0] + ofs, s[1]), (dr[0] + ofs, dr[1])
    d.add(elm.Line().at(s).to(a).color("gray").linewidth(1))
    d.add(elm.Line().at(dr).to(b).color("gray").linewidth(1))
    d.add(elm.Diode().at(a).to(b).color("gray").linewidth(1))


def draw(fmt):
    schemdraw.use("matplotlib" if fmt == "png" else "svg")
    d = schemdraw.Drawing(show=False)
    d.config(unit=2, fontsize=10, lw=1.6)

    def cap_to_n(x, text):
        d.add(elm.Dot().at((x, YT)))
        d.add(elm.Capacitor().at((x, YT)).to((x, YN)).label(text, loc="bottom", fontsize=9))
        d.add(elm.Dot().at((x, YN)))

    def mov(x, text):
        d.add(elm.Dot().at((x, YT)))
        d.add(elm.ResistorVarIEC().at((x, YT)).to((x, YN)).label(text, loc="bottom", fontsize=9))
        d.add(elm.Dot().at((x, YN)))

    def cm_choke(x0, x1, name):
        d.add(elm.Inductor2(loops=3).at((x0, YT)).to((x1, YT)).label(name, fontsize=9))
        d.add(elm.Inductor2(loops=3).at((x0, YN)).to((x1, YN)).flip())
        d.add(elm.Line().at((x0 + 0.35, YT - 0.75)).to((x1 - 0.35, YT - 0.75)).linewidth(1))
        d.add(elm.Line().at((x0 + 0.35, YT - 0.95)).to((x1 - 0.35, YT - 0.95)).linewidth(1))
        d.add(elm.Label().at(((x0 + x1) / 2, YT - 1.5)).label("common-mode\nchoke, both lines", fontsize=8))

    # ---------------- high-voltage port -> series switch ----------------
    d.add(elm.Dot(open=True).at((0, YT)).label("HV  L\n277 V / 230 V", loc="left", fontsize=10))
    d.add(elm.Dot(open=True).at((0, YN)).label("N", loc="left", fontsize=10))
    d.add(elm.Fuse().at((0, YT)).to((2, YT)).label("F1\n80 A", fontsize=9))
    d.add(elm.Switch().at((2, YT)).to((4, YT)).label("K1", fontsize=9))
    d.add(elm.Line().at((4, YT)).to((5.5, YT)))
    mov(4.7, "RV1\n320 Vac")
    cm_choke(5.5, 7.5, "L2")
    d.add(elm.Line().at((7.5, YT)).to((9, YT)))
    cap_to_n(8.3, "C3\n2.2 uF X2")
    d.add(elm.ResistorIEC().at((9, YT)).to((10.6, YT)).label("CS1", fontsize=9))
    d.add(elm.Line().at((10.6, YT)).to((12.2, YT)))
    cap_to_n(11.4, "C1\n10 uF film\n+ 1 uF low-ESL")
    d.add(elm.Label().at((11.4, YT + 0.5)).label("V_HV", fontsize=8, color="tab:blue"))

    # series bidirectional switch: Q1 (drain to HV) and Q2 (drain to SW), common source
    q1 = d.add(elm.NFet(bulk=False).theta(90).anchor("drain").at((12.2, YT)).label("Q1  6x", loc="left", ofst=(0.75, 0.9), fontsize=9))
    q2 = d.add(elm.NFet(bulk=False).theta(90).flip().anchor("source").at(q1.source).label("Q2  6x", loc="right", ofst=(-0.75, 0.9), fontsize=9))
    body_diode(d, q1, True, -0.9)
    body_diode(d, q2, True, -0.9)
    d.add(elm.Dot().at(q1.source))
    d.add(elm.Label().at((q1.source[0], YT - 1.75)).label("common source\n(driver A reference)", fontsize=8))
    xsw = q2.drain[0] + 1.3
    d.add(elm.Line().at(q2.drain).to((xsw, YT)))
    d.add(elm.Dot().at((xsw, YT)).label("SW", loc="top", fontsize=9))

    # shunt bidirectional switch: Q3 (drain to SW) and Q4 (drain to N), common source
    q3 = d.add(elm.NFet(bulk=False).anchor("drain").at((xsw, YT - 1.2)).label("Q3  6x", loc="right", ofst=(0.5, 0.75), fontsize=9))
    d.add(elm.Line().at((xsw, YT)).to(q3.drain))
    q4 = d.add(elm.NFet(bulk=False).theta(180).reverse().anchor("source").at((xsw, q3.source[1] - 1.0)).label("Q4  6x", loc="right", ofst=(0.5, -0.75), fontsize=9))
    d.add(elm.Line().at(q3.source).to(q4.source))
    d.add(elm.Dot().at((xsw, q3.source[1] - 0.5)))
    d.add(elm.Line().at(q4.drain).to((xsw, YN)))
    d.add(elm.Dot().at((xsw, YN)))
    body_diode(d, q3, False, -0.9)
    body_diode(d, q4, False, -0.9)

    # gate drivers
    xa = q1.source[0]
    d.add(flow.Box(w=5.2, h=1.5).at((xa - 2.6, YT + 3.4)).anchor("W").label("Isolated supply A\n+ gate drivers GD1, GD2", fontsize=9))
    d.add(elm.Line().at(q1.gate).to((q1.gate[0], YT + 2.65)).linestyle("--").linewidth(1))
    d.add(elm.Line().at(q2.gate).to((q2.gate[0], YT + 2.65)).linestyle("--").linewidth(1))
    xb = xsw + 2.3
    yb = (q3.source[1] + q4.source[1]) / 2
    d.add(flow.Box(w=3.6, h=2.0).at((xb, yb)).anchor("W").label("Isolated supply B\n+ gate drivers\nGD3, GD4", fontsize=9))
    d.add(elm.Line().at(q3.gate).to((xb, q3.gate[1])).linestyle("--").linewidth(1))
    d.add(elm.Line().at(q4.gate).to((xb, q4.gate[1])).linestyle("--").linewidth(1))
    d.add(elm.Line().at((xb, q3.gate[1])).to((xb, yb + 1.0)).linestyle("--").linewidth(1))
    d.add(elm.Line().at((xb, q4.gate[1])).to((xb, yb - 1.0)).linestyle("--").linewidth(1))

    # ---------------- inductor -> low-voltage port ----------------
    x = xsw
    d.add(elm.Inductor2(loops=4).at((x, YT)).to((x + 3, YT)).label("L1  20 uH\ngapped ferrite", fontsize=9))
    d.add(elm.ResistorIEC().at((x + 3, YT)).to((x + 4.6, YT)).label("CS2  (I_L)", fontsize=9))
    x += 4.6
    d.add(elm.Line().at((x, YT)).to((x + 7.4, YT)))
    d.add(elm.Dot().at((x + 2.4, YT)))
    d.add(elm.Capacitor().at((x + 2.4, YT)).to((x + 2.4, YN)).label("C2\n20 uF\nfilm", loc="bottom", fontsize=9))
    d.add(elm.Dot().at((x + 2.4, YN)))
    d.add(elm.Label().at((x + 2.4, YT + 0.5)).label("V_LV", fontsize=8, color="tab:blue"))
    xc = x + 4.6
    d.add(elm.Dot().at((xc, YT)))
    tr = d.add(elm.Triac().at((xc, YT)).to((xc, YN)).label("TR1\ncrowbar", loc="bottom", ofst=0.35, fontsize=9))
    d.add(elm.Dot().at((xc, YN)))
    d.add(flow.Box(w=2.4, h=1.2).at((xc + 1.0, YT / 2 - 1.8)).anchor("W").label("OV trip\n(hardware)", fontsize=8))
    d.add(elm.Line().at(tr.gate).to((xc + 1.0, YT / 2 - 1.8)).linestyle("--").linewidth(1))
    x += 7.4
    x_l3 = x
    cm_choke(x, x + 2, "L3")
    x += 2
    d.add(elm.Line().at((x, YT)).to((x + 4.4, YT)))
    cap_to_n(x + 1.0, "C4\n2.2 uF X2")
    mov(x + 3.4, "RV2\n150 Vac")
    x += 4.4
    d.add(elm.Switch().at((x, YT)).to((x + 2, YT)).label("K2", fontsize=9))
    d.add(elm.Fuse().at((x + 2, YT)).to((x + 4, YT)).label("F2\n150 A", fontsize=9))
    x += 4
    d.add(elm.Dot(open=True).at((x, YT)).label("LV  L\n120 V", loc="right", fontsize=10))
    d.add(elm.Dot(open=True).at((x, YN)).label("N", loc="right", fontsize=10))

    # neutral, straight through (interrupted only by the two CM-choke windings)
    d.add(elm.Line().at((0, YN)).to((5.5, YN)))
    d.add(elm.Line().at((7.5, YN)).to((x_l3, YN)))
    d.add(elm.Line().at((x_l3 + 2, YN)).to((x, YN)))
    d.add(elm.Label().at((xsw - 3.0, YN - 0.45)).label("neutral runs straight through: not switched, not fused", fontsize=8))
    d.add(elm.Label().at((x / 2, YT + 5.6)).label(
        "Non-isolated block: bidirectional AC chopper, 120 V <-> 277 V / 230 V, 10 kW continuous, 20 kW for 10 s", fontsize=12))

    # controller
    d.add(flow.Box(w=x - 4.0, h=2.2).at((2.0, YN - 2.6)).anchor("W").label(
        "Controller (MCU):  PWM at 50 kHz, polarity-based commutation, ratio select 277 V / 230 V, current limit, protection, contactor control\n"
        "Inputs: V_HV, V_LV, CS1, CS2, NTC on each switch group, L1 and heatsink      "
        "Telemetry: isolated CAN FD + Ethernet (V, I, T, P, Q, energy, state, faults)", fontsize=9))
    d.save(os.path.join(OUT, f"schematic_noniso.{fmt}"), dpi=140) if fmt == "png" else d.save(os.path.join(OUT, f"schematic_noniso.{fmt}"))


if __name__ == "__main__":
    draw("png")
    draw("svg")
