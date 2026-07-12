"""ON/OFF cycle matching + periodicity + energy (spec §6, §6b, §7)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .clustering import Cluster, auto_label
from .detector import Event


@dataclass
class Cycle:
    cluster: int        # ON-cluster id
    t_on: float
    t_off: float
    dp: float           # plateau VA

    @property
    def duration_s(self) -> float:
        return self.t_off - self.t_on

    def energy_kwh(self, pf: float = 1.0) -> float:
        return self.dp * self.duration_s * pf / 3.6e6


@dataclass
class ApplianceStats:
    cid: int
    label: str
    dp: float
    spike_ratio: float
    n_on: int
    n_cycles: int
    match_rate: float
    median_dur_s: float
    period_cv: float | None
    duty: float | None
    energy_kwh: float
    pf: float


def pair_clusters(on: list[Cluster], off: list[Cluster],
                  eps_rel: float = 0.15) -> dict[int, int]:
    """Pair each ON cluster with the OFF cluster of nearest |ΔP| (spec §6.1)."""
    pairs: dict[int, int] = {}
    used: set[int] = set()
    for c in sorted(on, key=lambda c: -c.n):          # biggest evidence first
        best, best_err = None, eps_rel
        for o in off:
            if o.cid in used:
                continue
            err = abs(c.dp - o.dp) / max(c.dp, 1.0)
            if err < best_err:
                best, best_err = o, err
        if best is not None:
            pairs[c.cid] = best.cid
            used.add(best.cid)
    return pairs


def match_cycles(on_events: list[Event], off_events: list[Event],
                 on_labels: np.ndarray, off_labels: np.ndarray,
                 pairs: dict[int, int],
                 eps_abs: float = 25.0, eps_rel: float = 0.12,
                 d_min: float = 60.0, d_max: float = 8 * 3600.0
                 ) -> tuple[list[Cycle], list[Event]]:
    """Greedy chronological FSM matching (spec §6.2). Returns (cycles, orphans)."""
    stream: list[tuple[float, Event, int]] = (
        [(e.t_start, e, int(lab)) for e, lab in zip(on_events, on_labels)] +
        [(e.t_start, e, int(lab)) for e, lab in zip(off_events, off_labels)]
    )
    stream.sort(key=lambda r: r[0])
    off_to_on = {v: k for k, v in pairs.items()}
    open_on: dict[int, Event] = {}                    # ON-cluster id -> pending ON event
    cycles: list[Cycle] = []
    orphans: list[Event] = []

    for t, ev, lab in stream:
        if ev.is_on:
            if lab in pairs:
                if lab in open_on:                    # missed OFF: drop stale ON
                    orphans.append(open_on[lab])
                open_on[lab] = ev
            else:
                orphans.append(ev)
        else:
            on_cid = off_to_on.get(lab)
            pending = open_on.get(on_cid) if on_cid is not None else None
            if pending is not None:
                dur = ev.t_start - pending.t_start
                tol = max(eps_abs, eps_rel * pending.dp)
                if d_min <= dur <= d_max and abs(pending.dp + ev.dp) < tol:
                    cycles.append(Cycle(on_cid, pending.t_start, ev.t_start, pending.dp))
                    del open_on[on_cid]
                    continue
            orphans.append(ev)

    orphans.extend(open_on.values())                  # never-closed ONs
    return cycles, orphans


def periodicity(cycles: list[Cycle]) -> tuple[float | None, float | None]:
    """(CV of inter-ON intervals, duty cycle) — robust via MAD (spec §6b)."""
    if len(cycles) < 5:
        return None, None
    t_on = np.sort(np.array([c.t_on for c in cycles]))
    gaps = np.diff(t_on)
    gaps = gaps[gaps < 4 * np.median(gaps)]           # ignore door-open / defrost outliers
    if len(gaps) < 4:
        return None, None
    mad = np.median(np.abs(gaps - np.median(gaps))) * 1.4826
    cv = float(mad / np.median(gaps))
    duty = float(np.median([c.duration_s for c in cycles]) / np.median(gaps))
    return cv, duty


def summarize(on_clusters: list[Cluster], cycles: list[Cycle]
              ) -> list[ApplianceStats]:
    out = []
    for c in on_clusters:
        cyc = [x for x in cycles if x.cluster == c.cid]
        cv, duty = periodicity(cyc)
        med_dur = float(np.median([x.duration_s for x in cyc])) if cyc else 0.0
        pf = 0.8 if c.is_motor else 1.0
        out.append(ApplianceStats(
            cid=c.cid,
            label=auto_label(c.dp, c.spike_ratio, cv, duty, med_dur or None),
            dp=c.dp, spike_ratio=c.spike_ratio,
            n_on=c.n, n_cycles=len(cyc),
            match_rate=len(cyc) / c.n if c.n else 0.0,
            median_dur_s=med_dur, period_cv=cv, duty=duty,
            energy_kwh=sum(x.energy_kwh(pf) for x in cyc), pf=pf,
        ))
    return sorted(out, key=lambda s: -s.energy_kwh)
