"""Synthetic Linky-like PAPP generator for pipeline testing.

Simulates: 330 VA baseline, fridge (70 VA plateau + 200 VA inrush, ~45 min period),
kettle (1850 VA, ~3 min, few times/day), water heater (2200 VA, 6h nightly),
10 VA meter quantisation, 5 s sampling, change-only reporting.

    python -m nilm.synth --days 3 --out synth.csv   (also writes synth_truth.json)
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path


def generate(days: float = 3.0, period: float = 5.0, seed: int = 42,
             quant: float = 10.0):
    rng = random.Random(seed)
    T = int(days * 86400 / period)
    truth = {"fridge_cycles": 0, "kettle_runs": 0, "fridge_kwh": 0.0,
             "kettle_kwh": 0.0, "heater_kwh": 0.0}

    sig = [0.0] * T

    def add(start_s, dur_s, plateau, spike=0.0, spike_dur_s=0.0):
        i0, i1 = int(start_s / period), min(int((start_s + dur_s) / period), T)
        for i in range(i0, i1):
            sig[i] += plateau
        for i in range(i0, min(i0 + max(1, int(spike_dur_s / period)), T)):
            sig[i] += spike
        return plateau * max(0, i1 - i0) * period / 3.6e6   # clipped truth energy

    # fridge: period ~45 min +/- 4, on-time ~18 min +/- 2
    t = rng.uniform(0, 600)
    while t < days * 86400 - 1500:
        dur = rng.gauss(18 * 60, 120)
        truth["fridge_kwh"] += add(t, dur, 70 + rng.gauss(0, 3), spike=200, spike_dur_s=6)
        truth["fridge_cycles"] += 1
        t += rng.gauss(45 * 60, 240)

    # kettle: 4 runs/day at random daytime hours
    for d in range(int(days) + 1):
        for _ in range(4):
            t0 = d * 86400 + rng.uniform(6.5, 22) * 3600
            if t0 < days * 86400 - 400:
                truth["kettle_kwh"] += add(t0, rng.uniform(150, 240), 1850 + rng.gauss(0, 20))
                truth["kettle_runs"] += 1

    # water heater: nightly 23:30 -> ~05:30
    for d in range(int(days)):
        truth["heater_kwh"] += add(d * 86400 + 23.5 * 3600, 6 * 3600, 2200)

    times, values = [], []
    prev = None
    for i in range(T):
        x = 330 + sig[i] + rng.gauss(0, 2)
        x = quant * round(x / quant)                       # meter quantisation
        if x != prev:                                      # change-only reporting
            times.append(1750000000 + i * period)
            values.append(x)
            prev = x
    return times, values, truth


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=float, default=3.0)
    ap.add_argument("--period", type=float, default=5.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path("synth.csv"))
    a = ap.parse_args(argv)

    times, values, truth = generate(a.days, a.period, a.seed)
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "value"])
        w.writerows(zip(times, values))
    truth_path = a.out.with_name(a.out.stem + "_truth.json")
    truth_path.write_text(json.dumps(truth, indent=2))
    print(f"wrote {a.out} ({len(times)} change-rows, {a.days} days) and {truth_path}")
    print(json.dumps(truth, indent=2))


if __name__ == "__main__":
    main()
