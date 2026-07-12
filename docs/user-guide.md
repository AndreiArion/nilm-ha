# NILM-HA User Guide

## How it works (30 seconds)

Your meter reports one number: total apparent power. Every appliance that
switches on or off produces a *step* in that signal. NILM-HA detects these
steps, groups steps of similar magnitude into *appliance signatures*, pairs
each ON step with its matching OFF step into *cycles*, and integrates
`power x duration` into per-appliance energy. No training data, no cloud, no ML
runtime — everything is derived from edges in your own signal. Full math and
architecture: [`nilm_load_disaggregation_spec.adoc`](nilm_load_disaggregation_spec.adoc).

## Prerequisites

| Requirement | Why |
|---|---|
| Meter power sensor updating every **2–5 s** | The whole method reads step edges; at 60 s cadence short appliances (kettle) are invisible and edges blur |
| Sensor reports on **every change** (small deadband) | A 10+ VA deadband hides small appliances |
| Home Assistant ≥ 2024.6 | Uses current config-flow / sensor APIs |

For a **LiXee ZLinky_TIC on Zigbee2MQTT**: device → *Reporting* →
`haElectricalMeasurement / apparentPower` → min **5 s**, max **300 s**, min change **1**.
The poll-interval options in the device settings do *not* affect PAPP (it is a
reportable attribute). Linky *mode historique* quantises to 10 VA; switching the
meter to *mode standard* (free, Enedis F185 via your supplier) improves this to
1 VA — note the source entity changes from `PAPP` to `SINSTS`/`apparent_power`.

## Configuration parameters

Set at install (Settings → Devices & services → Add integration → NILM):

| Parameter | Default | Meaning | Tune when |
|---|---|---|---|
| Meter sensor | — | The whole-house VA/W sensor | — |
| Sampling period | 5 s | Internal uniform-grid resample; match your feed cadence | Feed faster/slower than 5 s |
| Steadiness band `t_ss` | 25 VA | Signal is "steady" when max−min over ~5 samples is below this | Raise if events fire with nothing switching; lower (to ~8) on a 1 VA feed |
| CUSUM slack `kappa` | 15 VA | Half the smallest step you care about (2×kappa ≈ 30 VA minimum appliance) | Lower to catch smaller loads (more noise events) |
| CUSUM threshold `h` | 30 VA | Alarm threshold: higher = fewer false events, slower detection | Raise if noisy nights produce phantom events |

To change parameters later: remove and re-add the integration (options flow is
on the roadmap). Learned appliances are stored separately and survive restarts;
remove `.storage/nilm.<entry_id>` to reset the model.

## Entities

| Entity | Meaning |
|---|---|
| `Baseline power` | Always-on floor (rolling 24 h minimum): router, standby loads |
| `Attributed power` | Sum of the steady draw of appliances currently detected ON |
| `Unattributed power` | Total − baseline − attributed. **The quality KPI**: should trend down over the first weeks |
| `Detected events` | Count of edges seen (attribute `last_event`: ΔP, spike, rise time) |
| `Appliance N power` | VA while the appliance is ON, else 0. Attributes: step VA, event/cycle counts, spike ratio (>0.2 ⇒ motor), last cycle duration |
| `Appliance N energy` | Cumulative kWh (`total_increasing`) — add it to the Energy dashboard |

Appliance entities appear only after a signature has been seen **4 times**.
Rename them as you identify appliances (the attributes help: a ~70 VA step
with spike ratio > 0.2 cycling every 45 min is your fridge).

## Identifying appliances

1. Wait a few hours; the fridge is usually `appliance_0`.
2. Trigger appliances one at a time (kettle, microwave, oven) with an eye on
   `Detected events` — the `last_event` attribute shows the step size each one makes.
3. Rename the matching entities. Typical signatures:

| Appliance | Step | Pattern |
|---|---|---|
| Fridge/freezer | 40–250 VA | Regular ~30–60 min cycles, motor spike |
| Kettle | 1–2.5 kVA | 2–4 min, irregular |
| Microwave | 1–1.5 kVA | 1–3 min |
| Water heater (HC) | 1–3 kVA | Hours, often nightly |
| Washing machine / dishwasher | mixed | Several signatures (heater + motor) — v0 shows them as separate appliances |

## Troubleshooting

**No events at all** — check the source sensor updates every few seconds
(Developer tools → States, watch it while boiling a kettle). If it updates
once a minute, fix the reporting config (see Prerequisites).

**Events but no appliances** — each appliance needs ≥ 4 occurrences. The fridge
arrives within hours; a water heater needs 4 days if it runs once a day.

**Phantom events at night** — raise `h` (e.g. 40–50) and/or `t_ss`.

**Two appliances merged into one** (similar wattage, e.g. kettle vs heater
plate) — a known v0 limitation; duration-based separation is on the roadmap
(PLAN.md M2). Energy attribution still lands on the right total.

**Unattributed stays high (> 40% after 2 weeks)** — expected contributors:
variable-power devices (induction hob, inverter heat-pumps, dimmers) are
structurally invisible to edge detection; everything else suggests thresholds
too high for your noise floor.

**Energy numbers look ~10–20% off vs a smart plug** — the Linky reports VA
(apparent power); real W = VA × power factor. Motor clusters use PF 0.8,
resistive 1.0. Calibration against the meter energy index is on the roadmap.

## Offline tuning (recommended before/alongside live use)

Export the sensor history to CSV (History → entity → download, or SQL — see
PLAN.md) and run the replay tool on a PC to see exactly what the live
integration would detect, iterating on thresholds in seconds:

```bash
pip install numpy
python3 -m nilm.replay papp.csv --period 5 --t-ss 25 --kappa 15 --h 30
```

It prints the discovered appliance table and writes `events.csv`, `cycles.csv`,
`clusters.json` for inspection. Feed the values that work back into the
integration setup.
