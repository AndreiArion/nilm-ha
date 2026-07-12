# nilm-ha

Non-Intrusive Load Monitoring (NILM) for Home Assistant: disaggregate a single
Linky teleinfo `PAPP` (apparent power) feed into per-appliance power & energy
sensors, using classical event-based NILM (Hart 1992): edge detection (CUSUM +
steady-state) -> signature clustering -> ON/OFF cycle matching -> energy attribution.

- **`PLAN.md`** — project plan, status, decisions log (start here to resume work)
- **`docs/nilm_load_disaggregation_spec.adoc`** — full specification (math,
  architecture, HA integration design). Render with `asciidoctor -r asciidoctor-diagram`.
- **`nilm/`** — offline core (pure Python + numpy, no HA imports)

## Quick start

```bash
# self-test on synthetic data (fridge + kettle + water heater, ground truth included)
python3 -m nilm.synth --days 3 --out synth.csv
python3 -m nilm.replay synth.csv

# real data: export sensor history to CSV (see PLAN.md), then
python3 -m nilm.replay papp.csv --period 5
```

Status: M1 (offline core) done — 98.6% fridge cycle recall, 99% energy accuracy
on synthetic data. Next: tune on real 5 s Linky data (M2), then wrap as an HA
custom integration (M3). See PLAN.md.
