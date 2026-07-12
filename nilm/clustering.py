"""Signature clustering (spec §5). Pure numpy DBSCAN — no sklearn needed."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .detector import Event


def features(events: list[Event]) -> np.ndarray:
    """z = (log|ΔP|, spike_ratio, log1p(rise_s)) — spec §5.1."""
    return np.array(
        [[math.log(abs(e.dp)), e.spike_ratio, math.log1p(e.rise_s)] for e in events]
    )


def dbscan(Z: np.ndarray, eps: float, min_pts: int) -> np.ndarray:
    """Minimal O(n^2) DBSCAN. Fine for <= ~20k events. Labels: -1 = noise."""
    n = len(Z)
    if n == 0:
        return np.array([], dtype=int)
    d2 = ((Z[:, None, :] - Z[None, :, :]) ** 2).sum(-1)
    neigh = [np.flatnonzero(row <= eps * eps) for row in d2]
    labels = np.full(n, -1, dtype=int)
    cluster = 0
    for i in range(n):
        if labels[i] != -1 or len(neigh[i]) < min_pts:
            continue
        labels[i] = cluster
        seeds = list(neigh[i])
        k = 0
        while k < len(seeds):
            j = seeds[k]
            k += 1
            if labels[j] == -1:
                labels[j] = cluster
                if len(neigh[j]) >= min_pts:
                    seeds.extend(x for x in neigh[j] if labels[x] == -1)
        cluster += 1
    return labels


@dataclass
class Cluster:
    cid: int
    sign: int                       # +1 ON cluster, -1 OFF cluster
    dp: float                       # median |ΔP| (VA)
    spike_ratio: float
    rise_s: float
    n: int
    event_idx: list[int] = field(default_factory=list)  # indices into event list

    @property
    def is_motor(self) -> bool:
        return self.spike_ratio > 0.2


# Feature weights: ΔP dominates. Spike is EXCLUDED from the distance (weight 0):
# at ~5 s sampling a 1-2 sample inrush is only *sometimes* captured (median
# filter, sample phase), and a stochastic feature must not split an appliance
# into several clusters. It remains in Cluster stats & auto-labelling.
# Revisit (e.g. 0.3-0.5) once the feed is 1-2 s / 1 VA (Linky mode standard).
FEATURE_WEIGHTS = np.array([1.0, 0.0, 0.3])


def cluster_events(events: list[Event], eps: float = 0.4, min_pts: int = 4
                   ) -> tuple[list[Cluster], np.ndarray]:
    """Cluster same-sign events. Returns (clusters, labels aligned to events)."""
    if not events:
        return [], np.array([], dtype=int)
    Z = features(events)
    mu, sd = Z.mean(axis=0), Z.std(axis=0) + 1e-9
    labels = dbscan((Z - mu) / sd * FEATURE_WEIGHTS, eps, min_pts)
    sign = 1 if events[0].dp > 0 else -1
    clusters = []
    for c in sorted(set(labels) - {-1}):
        idx = [i for i, l in enumerate(labels) if l == c]
        evs = [events[i] for i in idx]
        clusters.append(Cluster(
            cid=c, sign=sign,
            dp=float(np.median([abs(e.dp) for e in evs])),
            spike_ratio=float(np.median([e.spike_ratio for e in evs])),
            rise_s=float(np.median([e.rise_s for e in evs])),
            n=len(evs), event_idx=idx,
        ))
    return clusters, labels


def auto_label(dp: float, spike_ratio: float, period_cv: float | None,
               duty: float | None, median_dur_s: float | None) -> str:
    """Heuristic label suggestions (spec §7 table). Never authoritative."""
    if period_cv is not None and duty is not None:
        if 40 <= dp <= 250 and period_cv < 0.35 and 0.15 <= duty <= 0.65:
            return "fridge/freezer?"
    if dp >= 1000 and median_dur_s and median_dur_s > 3600:
        return "water-heater?"
    if dp >= 800 and median_dur_s and median_dur_s < 900:
        return "kettle/microwave/oven-element?"
    if spike_ratio > 0.2 and dp >= 250:
        return "motor-appliance? (washer/dishwasher pump)"
    return "unknown"
