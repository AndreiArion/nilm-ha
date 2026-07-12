"""Edge/event detection for NILM (spec §4: steady-state + CUSUM hybrid).

Pure Python, no HA imports. Feed uniformly resampled samples via push();
it emits Event objects on detected power steps.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from statistics import median


@dataclass
class Event:
    t_start: float          # epoch s, start of transition
    t_end: float            # epoch s, signal settled again
    dp: float               # ΔP steady-state, signed VA
    spike: float            # inrush overshoot above settled level, VA (>=0)
    rise_s: float           # settling time, s
    pre_level: float = 0.0  # steady level before the event, VA
    post_level: float = 0.0

    @property
    def is_on(self) -> bool:
        return self.dp > 0

    @property
    def spike_ratio(self) -> float:
        return self.spike / abs(self.dp) if self.dp else 0.0


@dataclass
class EdgeDetector:
    """O(1)-per-sample hybrid edge detector (spec §4.1-4.4)."""

    period: float = 5.0     # resample period T (s)
    t_ss: float = 25.0      # steadiness band (VA); ~3-4x noise std (10 VA quantised feed)
    kappa: float = 15.0     # CUSUM slack = delta_min / 2
    h: float = 30.0         # CUSUM threshold ~4-5 sigma
    win: int = 5            # median window w
    max_transition_s: float = 300.0  # give up / re-anchor after this

    _buf: deque = field(default_factory=lambda: deque(maxlen=64), repr=False)
    _gp: float = field(default=0.0, repr=False)
    _gm: float = field(default=0.0, repr=False)
    _mu: float | None = field(default=None, repr=False)
    _in_event: bool = field(default=False, repr=False)
    _pre_level: float = field(default=0.0, repr=False)
    _ev_t0: float = field(default=0.0, repr=False)
    _ev_samples: list = field(default_factory=list, repr=False)

    def _steady(self) -> bool:
        w = list(self._buf)[-self.win:]
        return len(w) == self.win and max(w) - min(w) < self.t_ss

    def _level(self) -> float:
        return median(list(self._buf)[-self.win:])

    def push(self, t: float, x: float) -> Event | None:
        """Feed one uniformly-sampled value. Returns an Event when one closes."""
        self._buf.append(x)

        if self._mu is None:                       # bootstrapping: wait for steadiness
            if self._steady():
                self._mu = self._level()
            return None

        if not self._in_event:
            self._gp = max(0.0, self._gp + x - self._mu - self.kappa)
            self._gm = max(0.0, self._gm - x + self._mu - self.kappa)
            if self._gp > self.h or self._gm > self.h or not self._steady():
                self._in_event = True
                self._pre_level = self._mu
                self._ev_t0 = t
                self._ev_samples = [x]
            else:                                   # slow drift tracking
                self._mu += 0.02 * (x - self._mu)
            return None

        # --- inside a transition: wait until the signal settles again ---
        self._ev_samples.append(x)
        if self._steady():
            post = self._level()
            dp = post - self._pre_level
            ev = None
            if abs(dp) >= 2 * self.kappa:           # ignore micro-events
                if dp > 0:
                    peak = max(self._ev_samples)
                    spike = max(0.0, peak - post)
                else:
                    trough = min(self._ev_samples)
                    spike = max(0.0, post - trough) if trough < post - self.t_ss else 0.0
                ev = Event(self._ev_t0, t, dp, spike, t - self._ev_t0,
                           self._pre_level, post)
            self._mu, self._gp, self._gm = post, 0.0, 0.0
            self._in_event = False
            return ev
        if (t - self._ev_t0) > self.max_transition_s:
            self._mu, self._in_event = None, False  # re-anchor from scratch
        return None


def resample_zoh(times: list[float], values: list[float], period: float):
    """Zero-order-hold resample of change-only data to a uniform grid.

    Yields (t, x) tuples. Exact for change-only sources (spec §3.1).
    """
    if not times:
        return
    i, n = 0, len(times)
    t = times[0]
    while t <= times[-1]:
        while i + 1 < n and times[i + 1] <= t:
            i += 1
        yield t, values[i]
        t += period


def median3(seq: list[float]) -> list[float]:
    """Width-3 median filter, edge-preserving denoise (spec §3.2)."""
    if len(seq) < 3:
        return list(seq)
    out = [seq[0]]
    for a, b, c in zip(seq, seq[1:], seq[2:]):
        out.append(sorted((a, b, c))[1])
    out.append(seq[-1])
    return out
