"""End-to-end regression: synthetic home -> replay -> known appliances found."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nilm.replay import run  # noqa: E402
from nilm.synth import generate  # noqa: E402


def test_fridge_recall_and_energy():
    times, values, truth = generate(days=5.0, seed=3)
    r = run(times, values, period=5.0)

    fridge = [s for s in r["stats"] if 40 <= s.dp <= 250 and s.period_cv
              and s.period_cv < 0.35]
    assert fridge, "fridge cluster not found"
    f = fridge[0]
    assert f.n_cycles >= 0.9 * truth["fridge_cycles"]
    assert abs(f.energy_kwh - truth["fridge_kwh"]) / truth["fridge_kwh"] < 0.15


def test_energy_conservation():
    times, values, truth = generate(days=5.0, seed=3)
    r = run(times, values, period=5.0)
    # remainder should be a small share of total
    assert r["remainder_kwh"] < 0.10 * r["total_kwh"]
