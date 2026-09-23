from types import SimpleNamespace

from GramAddict.core import utils


class _Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now


def _device(clock, call_seconds):
    """deviceV2.info costs the next value in call_seconds (last one repeats)."""
    costs = list(call_seconds)

    class DeviceV2:
        @property
        def info(self):
            clock.now += costs.pop(0) if len(costs) > 1 else costs[0]
            return {}

    return SimpleNamespace(deviceV2=DeviceV2())


def _patch(monkeypatch, clock):
    monkeypatch.setattr(utils.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(utils, "sleep", lambda s: setattr(clock, "now", clock.now + s))


def test_returns_immediately_when_fast(monkeypatch):
    clock = _Clock()
    _patch(monkeypatch, clock)
    assert utils.wait_until_uiautomator_is_fast(_device(clock, [0.2]))
    assert clock.now < 1


def test_waits_through_slow_cold_start(monkeypatch):
    clock = _Clock()
    _patch(monkeypatch, clock)
    device = _device(clock, [18, 17, 16, 0.3])
    assert utils.wait_until_uiautomator_is_fast(device)
    assert clock.now > 50


def test_gives_up_after_budget(monkeypatch):
    clock = _Clock()
    _patch(monkeypatch, clock)
    assert not utils.wait_until_uiautomator_is_fast(_device(clock, [20]), budget=60)
    assert clock.now < 100
