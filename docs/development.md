# Development guide

## Repository layout

```
nilm/                      # offline core (numpy allowed) — algorithm source of truth
  detector.py              #   edge detection: CUSUM + steady-state, ZOH resampler
  clustering.py            #   feature extraction + DBSCAN (fixed physical scales)
  matcher.py               #   ON/OFF pairing, cycle FSM, periodicity, energy
  replay.py                #   CLI: CSV history -> report + artifacts
  synth.py                 #   synthetic home generator with ground truth
custom_components/nilm/    # HA integration (STDLIB ONLY — no numpy)
  detector.py              #   copy of nilm/detector.py — keep in sync!
  online.py                #   streaming counterpart of clustering+matcher
  coordinator.py           #   listener -> resampler -> detector -> model -> dispatch
  sensor.py                #   entities;  config_flow.py, const.py, __init__.py
tests/                     # pytest; test_online.py loads the integration modules
docs/                      # spec (asciidoc), user guide, this file
PLAN.md                    # project plan / decision log / session memory
```

Design rule: algorithms are developed and validated **offline first** (`nilm/`,
seconds-fast on CSV exports), then ported to the streaming model
(`custom_components/nilm/online.py`). `detector.py` is shared by literal copy
because HA custom components cannot import from outside their package — if you
touch one, copy it to the other (CI does not yet enforce this).

## Running tests & lint

```bash
pip install numpy pytest ruff
pytest -q        # 10 tests: detector units, online model, synthetic ground-truth regression
ruff check .
```

The regression tests generate a synthetic home (fridge + kettle + water heater,
known cycle counts and kWh) and assert >=90% fridge cycle recall, <15% energy
error, <10% unattributed. If you change detection/clustering/matching, these
tests tell you whether you broke attribution.

## CI

`.github/workflows/ci.yml`: ruff, pytest, hassfest (HA manifest/quality checks),
HACS validation (`ignore: brands` — custom integration, not in the brands repo).

## Release

1. Bump nothing manually — versions come from tags.
2. GitHub → Releases → new release, tag `vX.Y.Z`.
3. `release.yml` stamps `manifest.json` with `X.Y.Z`, zips
   `custom_components/nilm` → `nilm.zip`, attaches it (HACS `zip_release`).

## Testing in a live HA without HACS

```bash
rsync -r custom_components/nilm/ <ha-config>/custom_components/nilm/
# restart HA, then add the integration via Settings -> Devices & services
```

Watch the log: `logger: logs: custom_components.nilm: debug` shows cluster
restores and event processing.

## Roadmap pointers

See `PLAN.md` (milestones M2–M4) and spec §12. Highest-value next items:
duration-based cluster splitting (kettle vs heater), options flow for live
threshold tuning, energy-index calibration of per-appliance PF.
