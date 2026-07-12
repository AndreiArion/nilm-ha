"""Online model test — loaded from file to avoid importing HA via the package."""
import importlib.util
import sys
import types
from pathlib import Path

BASE = Path(__file__).parent.parent / "custom_components" / "nilm"

# stub the package so relative imports inside the modules resolve without HA
pkg = types.ModuleType("cc_nilm")
pkg.__path__ = [str(BASE)]
sys.modules["cc_nilm"] = pkg


def _load(name):
    spec = importlib.util.spec_from_file_location(f"cc_nilm.{name}", BASE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"cc_nilm.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_load("const")
detector = _load("detector")
online = _load("online")


def test_online_cluster_lifecycle():
    m = online.OnlineNilm()
    t = 0.0
    established = []
    for _ in range(5):                       # 5 fridge cycles
        _, new = m.feed(detector.Event(t, t + 10, 70.0, 150.0, 10.0))
        established += new
        _, _ = m.feed(detector.Event(t + 1200, t + 1210, -70.0, 0.0, 5.0))
        t += 2700
    assert len(m.clusters) == 1
    c = next(iter(m.clusters.values()))
    assert c.established and established == [c.cid]
    assert c.cycles == 5
    expected = 5 * 70 * 1200 * c.pf / 3.6e6
    assert abs(c.energy_kwh - expected) / expected < 0.15   # EMA drift tolerance


def test_roundtrip_persistence():
    m = online.OnlineNilm()
    m.feed(detector.Event(0, 10, 1800.0, 0.0, 5.0))
    m2 = online.OnlineNilm.from_dict(m.to_dict())
    assert len(m2.clusters) == 1
    assert not next(iter(m2.clusters.values())).is_on   # never restored mid-cycle
