# Isolated bidirectional AC-AC dual active bridge

85-285 Vrms in and out (1:1), 10 kW continuous, 100 kW for 10 s above 200 V (500 A
below), SiC, 70 kHz. One block of a three-phase, parallelable system.

* `docs/DESIGN.md` - the design report (architecture, frequency evaluation,
  transformer, control, compliance, open items).
* `tools/dab_design.py` - sizing model: thermal device sizing, frequency sweep,
  transformer optimiser, loss tables, cost/volume roll-up, non-isolated variant,
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
