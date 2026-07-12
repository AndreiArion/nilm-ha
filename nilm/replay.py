"""Offline replay harness: CSV history -> events -> clusters -> cycles -> report.

Usage:
    python -m nilm.replay history.csv [--period 5] [--out results_dir]

Accepted CSV shapes (auto-detected):
  * two columns: timestamp,value           (epoch s or ISO 8601)
  * HA UI "download data": entity_id,state,last_changed_ts (any column order)
  * SQLite export: state,last_updated_ts
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .clustering import cluster_events
from .detector import EdgeDetector, median3, resample_zoh
from .matcher import match_cycles, pair_clusters, summarize

TIME_KEYS = ("last_changed_ts", "last_updated_ts", "last_changed", "last_updated",
             "timestamp", "time", "t", "date")
VALUE_KEYS = ("state", "value", "papp", "power", "va", "x")


def _parse_time(s: str) -> float | None:
    s = s.strip()
    try:
        return float(s)                                   # epoch seconds
    except ValueError:
        pass
    for fix in (s, s.replace("Z", "+00:00")):
        try:
            dt = datetime.fromisoformat(fix)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    return None


def load_csv(path: Path) -> tuple[list[float], list[float]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        sys.exit("empty CSV")

    header = [h.strip().lower() for h in rows[0]]
    t_col = v_col = None
    for i, h in enumerate(header):
        if t_col is None and h in TIME_KEYS:
            t_col = i
        if v_col is None and h in VALUE_KEYS:
            v_col = i
    if t_col is not None and v_col is not None:
        data_rows = rows[1:]
    elif len(rows[0]) >= 2 and _parse_time(rows[0][0]) is not None:
        t_col, v_col, data_rows = 0, 1, rows               # headerless 2-column
    else:
        sys.exit(f"cannot identify time/value columns in header: {header}")

    times, values = [], []
    for r in data_rows:
        if len(r) <= max(t_col, v_col):
            continue
        t = _parse_time(r[t_col])
        try:
            v = float(r[v_col])
        except ValueError:
            continue                                       # 'unavailable' etc.
        if t is not None:
            times.append(t)
            values.append(v)
    order = np.argsort(times)
    return [times[i] for i in order], [values[i] for i in order]


def run(times: list[float], values: list[float], period: float, det_kwargs=None):
    grid = list(resample_zoh(times, values, period))
    ts = [t for t, _ in grid]
    xs = median3([x for _, x in grid])

    det = EdgeDetector(period=period, **(det_kwargs or {}))
    events = [ev for t, x in zip(ts, xs) if (ev := det.push(t, x))]

    on = [e for e in events if e.is_on]
    off = [e for e in events if not e.is_on]
    on_cl, on_lab = cluster_events(on)
    off_cl, off_lab = cluster_events(off)
    pairs = pair_clusters(on_cl, off_cl)
    cycles, orphans = match_cycles(on, off, on_lab, off_lab, pairs)
    stats = summarize(on_cl, cycles)

    span_h = (ts[-1] - ts[0]) / 3600 if len(ts) > 1 else 0.0
    trapezoid = getattr(np, "trapezoid", np.trapz)
    total_kwh = float(trapezoid(xs, ts)) / 3.6e6
    baseline_va = float(np.percentile(xs, 1))
    baseline_kwh = baseline_va * (ts[-1] - ts[0]) / 3.6e6
    attributed_kwh = sum(s.energy_kwh for s in stats)
    return {
        "span_h": span_h, "n_samples": len(ts), "n_events": len(events),
        "n_on": len(on), "n_off": len(off), "n_cycles": len(cycles),
        "n_orphans": len(orphans), "baseline_va": baseline_va,
        "total_kwh": total_kwh, "baseline_kwh": baseline_kwh,
        "attributed_kwh": attributed_kwh,
        "remainder_kwh": total_kwh - baseline_kwh - attributed_kwh,
        "stats": stats, "cycles": cycles, "events": events,
    }


def report(r: dict) -> str:
    L = [
        f"span {r['span_h']:.1f} h | {r['n_samples']} samples | "
        f"{r['n_events']} events ({r['n_on']} ON / {r['n_off']} OFF) | "
        f"{r['n_cycles']} cycles matched, {r['n_orphans']} orphan events",
        f"energy: total {r['total_kwh']:.2f} kWh = baseline {r['baseline_kwh']:.2f} "
        f"({r['baseline_va']:.0f} VA always-on) + attributed {r['attributed_kwh']:.2f} "
        f"+ remainder {r['remainder_kwh']:.2f} "
        f"[{100 * r['remainder_kwh'] / max(r['total_kwh'], 1e-9):.0f}% unexplained]",
        "",
        f"{'id':>3} {'label':<38} {'ΔP VA':>7} {'spike':>6} {'cycles':>6} "
        f"{'match%':>6} {'dur(min)':>8} {'CV':>5} {'duty':>5} {'kWh':>7}",
    ]
    for s in r["stats"]:
        L.append(
            f"{s.cid:>3} {s.label:<38} {s.dp:>7.0f} {s.spike_ratio:>6.2f} "
            f"{s.n_cycles:>6} {100 * s.match_rate:>5.0f}% {s.median_dur_s / 60:>8.1f} "
            f"{s.period_cv if s.period_cv is not None else float('nan'):>5.2f} "
            f"{s.duty if s.duty is not None else float('nan'):>5.2f} "
            f"{s.energy_kwh:>7.2f}"
        )
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--period", type=float, default=5.0)
    ap.add_argument("--t-ss", type=float, default=25.0)
    ap.add_argument("--kappa", type=float, default=15.0)
    ap.add_argument("--h", type=float, default=30.0)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)

    times, values = load_csv(a.csv)
    print(f"loaded {len(times)} rows from {a.csv}")
    r = run(times, values, a.period,
            dict(t_ss=a.t_ss, kappa=a.kappa, h=a.h))
    print(report(r))

    out = a.out or a.csv.parent / (a.csv.stem + "_nilm")
    out.mkdir(exist_ok=True)
    with open(out / "events.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_start", "t_end", "dp_va", "spike_va", "rise_s"])
        for e in r["events"]:
            w.writerow([f"{e.t_start:.0f}", f"{e.t_end:.0f}",
                        f"{e.dp:.1f}", f"{e.spike:.1f}", f"{e.rise_s:.1f}"])
    with open(out / "cycles.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cluster", "t_on", "t_off", "duration_s", "dp_va", "kwh"])
        for c in r["cycles"]:
            w.writerow([c.cluster, f"{c.t_on:.0f}", f"{c.t_off:.0f}",
                        f"{c.duration_s:.0f}", f"{c.dp:.1f}",
                        f"{c.energy_kwh():.4f}"])
    with open(out / "clusters.json", "w") as f:
        json.dump([vars(s) for s in r["stats"]], f, indent=2, default=float)
    print(f"\nwrote {out}/events.csv, cycles.csv, clusters.json")


if __name__ == "__main__":
    main()
