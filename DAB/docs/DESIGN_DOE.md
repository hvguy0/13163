# Non-isolated block redesigned for 99.06 % at 35 % load

Numbers come from `tools/chopper_doe.py`. As with the rest of this folder it is
a paper design: device data, resistances and standby power are estimates, and
at this efficiency level a few watts decide the result. Section 5 says how much
each assumption is worth.

Two things I have not verified and you should: the 99.06 % figure itself and
the test conditions that go with it, and whether the rule (written for
distribution transformers) would apply to a power-electronic block at all.

## 1. What the target means

Transformer standards define efficiency as output over output plus losses, at
35 % of rated load:

    3.5 kW out, 99.06 %  ->  at most 33.2 W of total loss, including standby

The cost-optimised chopper from `DESIGN_COST.md` manages about 98.4 % at that
point, roughly 57 W. Half of that was a flat 25 W allowance for control and
auxiliaries, which was harmless at 10 kW and is fatal here. Meeting the target
is therefore less about bigger switches than about three changes of approach.

## 2. What changed

1. **Soft switching at light load.** The inductor is reduced to 16 uH so that
   below about 40 % load its ripple current is larger than the load current.
   The current then reverses every switching cycle and the switches turn on at
   zero voltage. The controller raises the frequency above 50 kHz as load
   falls (60 kHz at 35 % load, about 105 kHz at 10 %) to hold that condition
   with the least ripple, and returns to 50 kHz, hard-switched, above about
   half load. The frequency never goes below 50 kHz.
2. **Every milliohm is counted.** Fuses, contactor contacts, both windings of
   both EMI chokes, busbars and capacitor ESR are now in the model with
   explicit resistance targets. They were about 1 W in the old model and are
   really 6 W at 35 % load and about 36 W at full load.
3. **Standby is budgeted item by item**, and held to 5.5 W: 2.5 W for
   controller, sensing and communications, 0.6 W for the gate supplies, 1.4 W
   for two contactor coils on economised hold, 1.0 W of auxiliary-supply loss.
   Fans stay off below 80 W of dissipation.

More silicon is the smallest part of it: 12 devices per group instead of 6.

## 3. Selected design

| Item | Value |
|---|---|
| Topology | Bidirectional AC chopper, as in `SCHEMATIC_NONISO.md` |
| Switches | 4 groups of 12 x 1200 V 40 mohm SiC, 48 devices, each group split into two sets of 6 with its own driver |
| Inductor L1 | 16 uH on 3 stacked E100/60/28 ferrite sets, 8 turns of 80 mm^2 litz, 11 mm total gap, 0.58 mohm, 4.6 kg |
| Switching frequency | 50 kHz minimum, raised automatically at light load |
| Standby | 5.5 W |
| Path resistance targets | 3 mohm total on the 120 V side, 6 mohm on the high side, 3 mohm ESR per capacitor bank |

| | 120 V to 277 V | 120 V to 230 V |
|---|---|---|
| **Efficiency at 35 % load** | **99.20 %** (28.2 W, 60 kHz) | **99.22 %** (27.5 W, 50 kHz) |
| Efficiency at 100 % load | 98.59 % (143 W) | 98.62 % (140 W) |
| 20 kW for 10 s | 463 W, junction 88 C | 467 W, junction 87 C |

I designed to 99.20 % instead of just clearing 99.06 %, which leaves about 5 W
of margin. The cheapest design that clears the bare target is 8 x 40 mohm per
group at $1,229, with almost none.

![Efficiency against load and loss breakdown](img/doe_efficiency.png)

Efficiency against load, 120 V to 277 V:

| Load | 10 % | 20 % | 35 % | 50 % | 75 % | 100 % |
|---|---|---|---|---|---|---|
| Efficiency | 98.52 % | 99.10 % | 99.20 % | 98.94 % | 98.73 % | 98.59 % |
| Loss | 15 W | 18 W | 28 W | 54 W | 97 W | 143 W |

The step down between 35 % and 50 % is where soft switching is lost.

## 4. Where the 28.2 W goes (35 % load, 120 V to 277 V)

| Item | 35 % load | 100 % load |
|---|---|---|
| Switch conduction | 9.6 W | 65.7 W |
| Standby | 5.5 W | 5.5 W |
| Fuses, contactors, EMI chokes, busbars | 3.5 W | 28.7 W |
| Gate drive | 3.2 W | 2.7 W |
| Capacitor ESR | 2.2 W | 7.4 W |
| Switching | 1.7 W | 20.8 W |
| Inductor copper | 1.2 W | 5.1 W |
| Inductor core | 1.2 W | 1.5 W |
| Fans | 0 | 6.0 W |
| **Total** | **28.2 W** | **143.3 W** |

Standby and the passive current path together are a third of the loss. They
are requirements on parts that the earlier designs treated as incidental.

## 5. How firm the result is

Each line changes one assumption and shows the 35 % efficiency that results:

| If this turns out worse | Efficiency at 35 % load |
|---|---|
| As designed | 99.20 % |
| Standby 3 W higher | 99.12 % |
| On-resistance 20 % higher | 99.15 % |
| Path resistance 50 % higher | 99.15 % |
| Switching loss doubled | 99.15 % |
| Inductor loss 50 % higher | 99.17 % |
| All five together | about 98.93 % |

The design survives any one of these and fails if all five go wrong at once.
The honest reading is that 99.06 % is achievable but has to be proven on
hardware, with standby power and the passive path as the items to watch.

## 6. Cost

| Item | Prototype | 1000 units |
|---|---|---|
| SiC switches | $576 | $312 |
| Gate drives | $144 | $72 |
| Inductor | $220 | $95 |
| Heatsink and fans | $84 | $37 |
| Port capacitors, snubber | $60 | $25 |
| Low-side crowbar | $150 | $45 |
| EMI filters (2 ports) | $380 | $160 |
| Contactors, fuses, surge | $350 | $130 |
| Sensing, control, aux supply | $550 | $190 |
| PCBs, busbars, enclosure | $400 | $180 |
| Assembly and test | $420 | $168 |
| **Total** | **$3,334** | **$1,414** |

That is $246 more than the cost-optimised chopper ($1,168) at volume, about
21 %. The cost model does not yet price the lower-loss parts that the standby
and path-resistance targets imply (economised or latching contactors,
lower-resistance chokes, a low-power controller); allow perhaps $50-100 more.

A design using six 16 mohm devices per group reaches 99.24 % with 24 devices
for about $1,636, if fewer parts matter more than cost.

## 7. Consequences elsewhere

* **Schematic.** Same circuit. L1 becomes 16 uH on three core sets, each switch
  group becomes two sets of six with a driver each (eight drivers), and
  contactors K1 and K2 need economised or latching coils.
* **Emissions.** The switching frequency now moves between 50 and about
  105 kHz with load. That spreads the spectrum, which helps, but the EMI
  filter must be designed for the whole range.
* **Full-load efficiency** is 98.6 %, better than the cost-optimised design's
  98.1 % under the old model, though the two are not directly comparable
  because this model counts losses the old one left out.
* **Isolated block.** It has eight devices in the current path, a transformer
  and two unfolders. Its best 35 % point so far is well under 99 %, and I do
  not expect it to reach 99.06 % without a different topology.

## 8. Open items

1. Confirm the regulatory figure, its test conditions and its applicability.
2. Replace estimated device data with datasheet values, especially output
   charge and turn-off energy, which set the soft-switching boundary.
3. Zero-voltage switching holds over 75 % of the line cycle at 277 V; near the
   voltage zero crossing the energy is too small. The model accounts for the
   residual loss but it has not been simulated at circuit level.
4. Variable-frequency control, zero-crossing commutation and current sharing
   among twelve paralleled devices are not simulated.
5. The inductor's ripple-current loss uses an assumed AC resistance factor of
   3; with an 11 mm gap, fringing loss needs a proper design.
