# Isolated bidirectional AC-AC dual active bridge

85-285 Vrms in and out (1:1), 10 kW continuous, 100 kW for 10 s, SiC, 70 kHz.

* `docs/DESIGN.md` - the design report (architecture, frequency evaluation,
  transformer, control, compliance, open items).
* `tools/dab_design.py` - sizing model: cell-count study, frequency sweep,
  transformer optimiser, loss and thermal tables. Writes `docs/results.json`
  and the plots in `docs/img/`.
* `tools/dab_sim.py` - switched-waveform check of the model and closed-loop
  simulation of unannounced power reversal.

```
pip install numpy matplotlib
cd tools && python3 dab_design.py && python3 dab_sim.py
```

This is a paper design. Nothing has been built or measured.
