# nilm-ha

[![CI](https://github.com/AndreiArion/nilm-ha/actions/workflows/ci.yml/badge.svg)](https://github.com/AndreiArion/nilm-ha/actions/workflows/ci.yml)

Non-Intrusive Load Monitoring (NILM) for Home Assistant: disaggregate a single
whole-house meter signal (e.g. Linky teleinfo `PAPP`, apparent power) into
per-appliance power & energy sensors. Classical event-based NILM (Hart 1992):
edge detection (CUSUM + steady-state) -> signature clustering -> ON/OFF cycle
matching -> energy attribution. Pure Python, no ML dependencies, runs on a Pi.

| | |
|---|---|
| **`PLAN.md`** | project plan, status, decisions log — start here to resume work |
| **`docs/nilm_load_disaggregation_spec.adoc`** | full spec (math, architecture); render with `asciidoctor -r asciidoctor-diagram` |
| **`nilm/`** | offline core + replay harness (numpy; for tuning on exported history) |
| **`custom_components/nilm/`** | the Home Assistant integration (stdlib only) |
| **`docs/user-guide.md`** | entities, parameters, appliance identification, troubleshooting |
| **`docs/development.md`** | repo layout, tests, CI, release process |

## Install in Home Assistant (HACS)

1. HACS -> three-dot menu -> **Custom repositories** -> add
   `https://github.com/AndreiArion/nilm-ha`, category **Integration**.
2. Install **NILM Load Disaggregation**, restart HA.
3. Settings -> Devices & services -> **Add integration** -> "NILM Load
   Disaggregation" -> pick your meter sensor (e.g. `sensor.compteurelectric_papp`).

Manual alternative: copy `custom_components/nilm/` into your HA `config/custom_components/`.

### Data feed prerequisites (important!)

The detector needs **~2-5 s updates** from the meter sensor. For a LiXee
ZLinky_TIC on Zigbee2MQTT: device -> Reporting ->
`haElectricalMeasurement/apparentPower` -> min interval **5 s**, max **300 s**,
min change **1 VA**. A 60 s feed will detect only long-running loads.

### What you get

- `sensor.nilm_baseline_power` — always-on floor (rolling 24 h low)
- `sensor.nilm_attributed_power` / `sensor.nilm_unattributed_power` — live split;
  unattributed share is the quality KPI
- `sensor.nilm_detected_events` — edge counter (attributes show the last event)
- Per discovered appliance (after >= 4 occurrences): `appliance_N power` (VA)
  and `appliance_N energy` (kWh, Energy-dashboard ready). Rename entities to
  label them ("Fridge", ...) — attributes carry the signature (step VA, cycles,
  spike ratio, last cycle duration) to help identification.

A fridge typically becomes visible within hours; give it 1-2 days before tuning.

## Offline tuning on exported history

```bash
# self-test on synthetic data (fridge + kettle + water heater, with ground truth)
python3 -m nilm.synth --days 5 --out synth.csv
python3 -m nilm.replay synth.csv

# real data (CSV export: see PLAN.md), 5 s feed:
python3 -m nilm.replay papp.csv --period 5
```

## Development

```bash
pip install numpy pytest ruff
pytest -q          # unit + regression tests (synthetic ground truth)
ruff check .
```

CI runs ruff, pytest, [hassfest](https://developers.home-assistant.io/blog/2020/04/16/hassfest/)
and HACS validation. Releases: publish a GitHub release tagged `vX.Y.Z` — the
workflow stamps the manifest version and attaches `nilm.zip` for HACS.

Status: M1 done (offline core: 98.6% fridge cycle recall, 99% energy accuracy,
~1% remainder on synthetic weeks) + v0 HA integration. Next: M2 tuning on real
data. See `PLAN.md`.

## License

[MIT](LICENSE)
