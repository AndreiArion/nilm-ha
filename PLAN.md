# NILM-HA — Project Plan & Memory

> **Purpose of this file:** persistent memory for the project. To resume in a new
> Claude session: share this folder and say *"Continue the NILM project — read
> PLAN.md first."* Update the status boxes and the log as you go.

Goal: Home Assistant custom integration that disaggregates the whole-house
Linky `PAPP` signal into per-appliance power/energy sensors.
Full technical spec: `../nilm_load_disaggregation_spec.adoc` (may also be in this
folder). Approach: classical event-based NILM (Hart 1992) — edge detection →
signature clustering → ON/OFF cycle matching → energy attribution.

## Current status (update me!)

**Last updated: 2026-07-12 — Milestone M1 done, waiting on real data (M0 step 3).**

## Hardware / data context

- Meter: Linky, **mode historique** (10 VA precision on PAPP). Mode standard
  requested? ☐ no ☐ yes, on: ______ (free, Enedis F185 via supplier, gives 1 VA
  via SINSTS — entity will change from PAPP to `apparent_power`!)
- Bridge: LiXee **ZLinky_TIC v1** on **Zigbee2MQTT**
- HA entity: `sensor.compteurelectric_papp` (VA, apparent power)
- 2026-07-12: Z2M reporting reconfigured — `haElectricalMeasurement/apparentPower`
  min **5 s** / max **300 s** / min change **1 VA** (was 60/900/1) — blue ✓ applied.
- Known appliance so far: fridge ≈ +70 VA plateau, ~30–60 min period (visible in history)

## Milestones

### M0 — Data readiness
- [x] Fix Z2M reporting to 5 s (2026-07-12)
- [ ] Verify recorded cadence in HA (min interval ≈ 5 s) — SQL in spec §2, or
      History CSV download. Check recorder isn't excluding/deadbanding the entity.
- [ ] Raise recorder retention: `recorder: purge_keep_days: 30` (default 10)
- [ ] Accumulate ≥ 1 week of 5 s history, export CSV (see "Exporting data" below)
- [ ] Optional: smart plug on fridge for 1 week (ground truth for M2)
- [ ] Optional: request Linky mode standard (1 VA precision)

### M1 — Offline core + replay harness  ✅ DONE 2026-07-12
- [x] `nilm/detector.py` — CUSUM + steady-state edge detector, ZOH resampler, median3
- [x] `nilm/clustering.py` — features, numpy DBSCAN, auto-labels
- [x] `nilm/matcher.py` — cluster pairing, cycle FSM matching, periodicity, energy
- [x] `nilm/replay.py` — CLI: CSV → report + events.csv/cycles.csv/clusters.json
- [x] `nilm/synth.py` — synthetic Linky-like data generator with ground truth
- [x] End-to-end test on synthetic 7-day data. Results:
      fridge 219/222 cycles (98.6%), fridge energy 99% accurate, remainder 1%.
      Known: kettle (1850 VA) & water heater (2200 VA) merge into one cluster —
      ΔP too close; fix planned in M2.

### M2 — Tune on real data  ← NEXT
- [ ] Run `python -m nilm.replay my_export.csv --period 5` on real history
- [ ] Sanity-check: fridge cluster found? CV < 0.35? match% > 90%?
- [ ] Tune `--t-ss/--kappa/--h` if false events or missed edges
      (10 VA quantised feed → start t_ss=25, kappa=15, h=30)
- [ ] Improvement: split clusters with bimodal cycle durations (kettle vs heater case)
- [ ] Improvement: unmatched-edge decomposition (merged simultaneous events, spec §6.3)
- [ ] Validate energy vs smart-plug ground truth (target < 15% error)
- [ ] Freeze parameter set → record here: ______

### M3 — HA custom integration (spec §9)
- [ ] Skeleton: manifest.json, config_flow (pick source entity + preset), coordinator
- [ ] Port M2-frozen core (detector/clustering/matcher unchanged — no HA imports)
- [ ] Online clustering (Mahalanobis gate + EMA drift, spec §5.3) instead of batch DBSCAN
- [ ] Nightly re-cluster job + storage (`helpers.storage.Store`, schema in spec §9.5)
- [ ] Dynamic entities per cluster + remainder/baseline sensors (spec §9.4)
- [ ] Services: label_appliance, merge_clusters, reset_model
- [ ] Energy dashboard integration (energy sensors, `total_increasing`)

### M4 — Validation & polish (spec §11)
- [ ] Conservation check: index kWh = baseline + Σ appliances + remainder (±2%)
- [ ] Remainder share trending < 30% after 2 weeks
- [ ] Unit tests on synth edge cases (meter restart, gaps, overlapping events)
- [ ] HACS packaging, README

## Exporting data for replay

Easiest (UI): History → select the PAPP entity → ⋮ → Download data (CSV works as-is).

Bigger exports (SQLite Web add-on or SSH):
```sql
.mode csv
.output papp.csv
SELECT 'timestamp' AS timestamp, 'value' AS value;
SELECT s.last_updated_ts, s.state FROM states s
WHERE s.metadata_id = (SELECT metadata_id FROM states_meta
                       WHERE entity_id='sensor.compteurelectric_papp')
  AND s.state NOT IN ('unknown','unavailable')
ORDER BY s.last_updated_ts;
```

Then: `python3 -m nilm.replay papp.csv --period 5`
(run from this folder; needs Python ≥ 3.10 + numpy)

Quick self-test without real data:
`python3 -m nilm.synth --days 3 --out synth.csv && python3 -m nilm.replay synth.csv`

## Key decisions log

| Date | Decision | Why |
|---|---|---|
| 2026-07-12 | Classical event-based NILM, not ML | works at 5 s cadence, explainable, no training data |
| 2026-07-12 | HA custom integration (pure Python + numpy) | user choice; HACS-installable |
| 2026-07-12 | Build offline core + replay before HA wrapper | iterate on algorithms in seconds, not days |
| 2026-07-12 | Spike feature EXCLUDED from cluster distance (weight 0) | at 5 s the 1–2 s inrush is captured stochastically → was splitting the fridge into 3 clusters. Revisit at 1–2 s / 1 VA feed |
| 2026-07-12 | ZOH resampling, median-3 filter, no moving average | exact for change-only data; preserves edges |

## Parameters (current defaults, for 5 s / 10 VA-quantised feed)

detector: period=5, t_ss=25 VA, kappa=15, h=30, win=5, max_transition=300 s
clustering: eps=0.4 (z-scored space), min_pts=4, feature_weights=(1.0, 0, 0.3)
matcher: eps_abs=25 VA, eps_rel=0.12, d_min=60 s, d_max=6 h
After mode standard (1 VA): try t_ss≈8, kappa≈10, h≈20, and spike weight 0.3–0.5.

## Session log

- **2026-07-12**: Spec written (`nilm_load_disaggregation_spec.adoc`). Diagnosed
  60 s/10 VA feed → fixed Z2M reporting to 5 s/1 VA (10 VA remains, meter-side).
  Confirmed PAPP is RP (reportable) on ZLinky — poll settings irrelevant to it.
  Built + tested offline core (M1). Next: collect 1 week of real 5 s data, then M2.
