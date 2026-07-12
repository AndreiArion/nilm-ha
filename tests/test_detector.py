"""Unit tests for the edge detector (pure stdlib, no HA)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nilm.detector import EdgeDetector, median3, resample_zoh  # noqa: E402


def _run(samples, period=5.0, **kw):
    det = EdgeDetector(period=period, **kw)
    events = []
    for i, x in enumerate(samples):
        if ev := det.push(i * period, x):
            events.append(ev)
    return events


def test_single_step_up_down():
    sig = [330] * 20 + [400] * 40 + [330] * 20
    evs = _run(sig)
    assert len(evs) == 2
    assert 60 <= evs[0].dp <= 80
    assert -80 <= evs[1].dp <= -60


def test_step_with_inrush_spike():
    sig = [330] * 20 + [540, 410] + [400] * 40 + [330] * 20
    evs = _run(sig)
    assert len(evs) == 2
    on = evs[0]
    assert 60 <= on.dp <= 80          # spike must NOT bias the plateau estimate
    assert on.spike > 80              # ...but must be captured as a feature


def test_noise_no_events():
    import random
    rng = random.Random(1)
    sig = [330 + 10 * round(rng.gauss(0, 0.4)) for _ in range(300)]
    assert _run(sig) == []


def test_micro_step_ignored():
    sig = [330] * 20 + [345] * 40 + [330] * 20   # 15 VA < 2*kappa
    assert _run(sig) == []


def test_resample_zoh_exact_on_changes():
    times = [0.0, 12.0, 13.0, 30.0]
    values = [100.0, 200.0, 300.0, 100.0]
    grid = dict(resample_zoh(times, values, 5.0))
    assert grid[10.0] == 100.0        # before the 12 s change
    assert grid[15.0] == 300.0
    assert grid[30.0] == 100.0


def test_median3_preserves_step_kills_glitch():
    assert median3([1, 1, 9, 1, 1]) == [1, 1, 1, 1, 1]
    assert median3([1, 1, 5, 5, 5]) == [1, 1, 5, 5, 5]
