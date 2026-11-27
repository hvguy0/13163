# Isolated bidirectional AC-AC dual active bridge

85-285 Vrms in and out (1:1), 10 kW continuous, 100 kW for 10 s above 200 V (500 A
below), SiC, 70 kHz. One block of a three-phase, parallelable system.

* `docs/DESIGN.md` - the design report (architecture, frequency evaluation,
  transformer, control, compliance, open items).
* `docs/DESIGN_20KW.md` - the 20 kW-peak variant of both the isolated and the
  non-isolated block (`tools/dab_design_20kw.py`).
* `docs/DESIGN_COST.md` - cost-optimised versions with prototype and 1000-unit
  cost (`tools/dab_cost.py`).
* `docs/SCHEMATIC_NONISO.md` - power-stage schematic of the non-isolated block
  (`tools/draw_noniso_schematic.py`, needs `schemdraw`).
* `docs/DESIGN_DOE.md` - non-isolated block redesigned for 99.06 % efficiency
  at 35 % load (`tools/chopper_doe.py`).
* `tools/dab_design.py` - sizing model: thermal device sizing, frequency sweep,
  transformer optimiser, loss tables, cost/volume roll-up, non-isolated AC-chopper
  variant (120 V to 277/230 V),
  scaling. Writes `docs/results.json`
  and the plots in `docs/img/`.
* `tools/dab_sim.py` - switched-waveform check of the model and closed-loop
  simulation of unannounced power reversal.
* `tools/dab_parallel.py` - current sharing of five mismatched blocks in
  parallel, with droop and bank-average trim.

```
pip install numpy matplotlib
cd tools && python3 dab_design.py && python3 dab_sim.py && python3 dab_parallel.py
```

This is a paper design. Nothing has been built or measured.
