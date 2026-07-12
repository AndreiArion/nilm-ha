"""Online (streaming) appliance model: lightweight clustering + cycle FSM.

Stdlib only — v0 of spec section 5.3/6. Clusters are matched by relative
steady-state power; a cluster becomes "established" (gets HA entities) after
MIN_EVENTS_ESTABLISHED ON events.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field

from .const import MIN_EVENTS_ESTABLISHED
from .detector import Event

REL_TOL = 0.15          # cluster assignment: |log(dp) - log(c.dp)| < log(1+REL_TOL)
OFF_ABS_TOL = 25.0      # VA, ON/OFF magnitude match
OFF_REL_TOL = 0.15
D_MIN_S = 60.0
D_MAX_S = 8 * 3600.0
EMA_ALPHA = 0.05


@dataclass
class OnlineCluster:
    cid: int
    dp: float                       # EMA of ON step magnitude (VA)
    n: int = 0                      # ON events seen
    spike_ratio: float = 0.0        # EMA
    is_on: bool = False
    t_on: float = 0.0
    energy_kwh: float = 0.0
    cycles: int = 0
    last_duration_s: float = 0.0

    @property
    def established(self) -> bool:
        return self.n >= MIN_EVENTS_ESTABLISHED

    @property
    def pf(self) -> float:
        return 0.8 if self.spike_ratio > 0.2 else 1.0

    @property
    def name(self) -> str:
        return f"appliance_{self.cid}"

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("cid", "dp", "n", "spike_ratio", "is_on", "t_on",
                 "energy_kwh", "cycles", "last_duration_s")}

    @classmethod
    def from_dict(cls, d: dict) -> "OnlineCluster":
        return cls(**d)


@dataclass
class OnlineNilm:
    clusters: dict[int, OnlineCluster] = field(default_factory=dict)
    next_cid: int = 0
    _hour_mins: deque = field(default_factory=lambda: deque(maxlen=24), repr=False)
    _cur_hour: int = field(default=-1, repr=False)
    _cur_min: float = field(default=float("inf"), repr=False)

    # ---------- baseline tracking (rolling 24h low) ----------
    def observe_power(self, x: float, t: float | None = None) -> None:
        hour = int((t if t is not None else time.time()) // 3600)
        if hour != self._cur_hour:
            if self._cur_hour >= 0:
                self._hour_mins.append(self._cur_min)
            self._cur_hour, self._cur_min = hour, x
        self._cur_min = min(self._cur_min, x)

    @property
    def baseline(self) -> float | None:
        vals = list(self._hour_mins) + (
            [self._cur_min] if self._cur_min != float("inf") else [])
        return min(vals) if vals else None

    # ---------- event handling ----------
    def _nearest(self, dp: float) -> OnlineCluster | None:
        best, best_d = None, math.log(1 + REL_TOL)
        for c in self.clusters.values():
            d = abs(math.log(dp) - math.log(c.dp))
            if d < best_d:
                best, best_d = c, d
        return best

    def feed(self, ev: Event) -> tuple[list[int], list[int]]:
        """Process one detected edge.

        Returns (changed_cids, newly_established_cids).
        """
        changed: list[int] = []
        new: list[int] = []
        if ev.is_on:
            c = self._nearest(ev.dp)
            if c is None:
                c = OnlineCluster(cid=self.next_cid, dp=ev.dp)
                self.clusters[c.cid] = c
                self.next_cid += 1
            was = c.established
            c.dp += EMA_ALPHA * (ev.dp - c.dp)
            c.spike_ratio += EMA_ALPHA * (ev.spike_ratio - c.spike_ratio)
            c.n += 1
            c.is_on, c.t_on = True, ev.t_start
            if c.established and not was:
                new.append(c.cid)
            changed.append(c.cid)
        else:
            mag = -ev.dp
            best, best_err = None, 1.0
            for c in self.clusters.values():
                if not c.is_on:
                    continue
                dur = ev.t_start - c.t_on
                if not (D_MIN_S <= dur <= D_MAX_S):
                    continue
                err = abs(c.dp - mag) / max(c.dp, 1.0)
                if err < best_err and (mag - c.dp) < max(OFF_ABS_TOL, OFF_REL_TOL * c.dp):
                    best, best_err = c, err
            if best is not None and best_err < OFF_REL_TOL + OFF_ABS_TOL / max(best.dp, 1.0):
                dur = ev.t_start - best.t_on
                best.energy_kwh += best.dp * dur * best.pf / 3.6e6
                best.cycles += 1
                best.last_duration_s = dur
                best.is_on = False
                changed.append(best.cid)
        return changed, new

    # ---------- aggregates for sensors ----------
    @property
    def attributed_power(self) -> float:
        return sum(c.dp for c in self.clusters.values() if c.established and c.is_on)

    # ---------- persistence ----------
    def to_dict(self) -> dict:
        return {"next_cid": self.next_cid,
                "clusters": [c.to_dict() for c in self.clusters.values()]}

    @classmethod
    def from_dict(cls, d: dict) -> "OnlineNilm":
        m = cls(next_cid=d.get("next_cid", 0))
        for cd in d.get("clusters", []):
            cd["is_on"] = False          # never restore mid-cycle across restarts
            c = OnlineCluster.from_dict(cd)
            m.clusters[c.cid] = c
        return m
