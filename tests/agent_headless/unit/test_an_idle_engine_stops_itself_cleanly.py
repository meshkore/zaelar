"""An engine nobody is using ends its own process, and every stop ends within a bounded time.

Two mechanisms, one promise — the process exits on its own, with status 0, instead of being killed:
  * `nucleo/idle_stop.py`: with `ZAELAR_IDLE_STOP_MIN` set, no real activity, no worker and no notice due soon
    → the server is asked to shut down gracefully (never a signal to itself);
  * `server/lifespan.py`: each shutdown step has a timeout and the whole shutdown a hard deadline.
"""
from __future__ import annotations

import asyncio
import importlib
import time

import pytest

from nucleo import idle_stop

MIN = 60_000
NOW = 1_800_000_000_000


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    idle_stop._reset_for_tests()
    monkeypatch.delenv("ZAELAR_IDLE_STOP_MIN", raising=False)
    yield
    idle_stop._reset_for_tests()


def test_quiet_for_the_whole_window_with_nothing_pending_is_a_stop():
    why = idle_stop.decide(NOW, NOW - 16 * MIN, NOW - 60 * MIN, False, None, 15 * MIN)
    assert why and "16 min" in why


@pytest.mark.parametrize("last, started, workers, next_due, window", [
    (NOW - 14 * MIN, NOW - 60 * MIN, False, None, 15 * MIN),      # real activity inside the window
    (None, NOW - 3 * MIN, False, None, 15 * MIN),                 # the process itself is younger than the window
    (NOW - 60 * MIN, NOW - 90 * MIN, True, None, 15 * MIN),       # a Brain Worker is running
    (NOW - 60 * MIN, NOW - 90 * MIN, False, (NOW + 10 * MIN) / 1000, 15 * MIN),   # a notice is due soon
    (NOW - 60 * MIN, NOW - 90 * MIN, False, None, 0),             # off (self-host default)
])
def test_anything_still_owed_keeps_the_engine_up(last, started, workers, next_due, window):
    assert idle_stop.decide(NOW, last, started, workers, next_due, window) is None


def test_a_notice_far_away_does_not_hold_the_engine():
    assert idle_stop.decide(NOW, None, NOW - 60 * MIN, False, (NOW + 3 * 60 * MIN) / 1000, 15 * MIN)


def test_the_stop_asks_the_server_once_and_only_when_enabled(monkeypatch):
    calls = []
    idle_stop.request_exit(lambda: calls.append(1))
    monkeypatch.setattr(idle_stop, "_readings", lambda: (None, False, None))
    monkeypatch.setattr(idle_stop, "_STARTED_MS", 0)
    assert idle_stop.maybe_stop() is False and calls == []          # no ZAELAR_IDLE_STOP_MIN: never
    monkeypatch.setenv("ZAELAR_IDLE_STOP_MIN", "15")
    assert idle_stop.maybe_stop() is True and calls == [1]
    assert idle_stop.maybe_stop() is False and calls == [1]         # once per process


def test_an_unreadable_worker_registry_counts_as_busy(monkeypatch):
    import sys
    import types
    broken = types.ModuleType("nucleo.dispatch.registry")

    def _boom():
        raise RuntimeError("unreadable")
    broken.has_active = _boom
    monkeypatch.setitem(sys.modules, "nucleo.dispatch.registry", broken)
    import nucleo.dispatch as dispatch_pkg
    monkeypatch.setattr(dispatch_pkg, "registry", broken, raising=False)
    _last, workers, _next = idle_stop._readings()
    assert workers is True


def test_a_shutdown_step_that_hangs_is_cut_and_the_next_one_still_runs(monkeypatch):
    lifespan = importlib.import_module("server.lifespan")
    monkeypatch.setattr(lifespan, "STEP_TIMEOUT_S", 0.2)
    ran = []

    async def _hangs():
        await asyncio.sleep(30)

    async def _main():
        t0 = time.monotonic()
        await lifespan._stop("hangs", lambda: _hangs())
        await lifespan._stop("next", lambda: ran.append("next"))
        return time.monotonic() - t0
    assert asyncio.run(_main()) < 2
    assert ran == ["next"]


def test_the_shutdown_deadline_exits_the_process_with_status_zero(monkeypatch):
    lifespan = importlib.import_module("server.lifespan")
    codes = []
    monkeypatch.setattr(lifespan.os, "_exit", lambda code: codes.append(code))
    t = lifespan._arm_deadline(0.1)
    t.join(2)
    assert codes == [0]
    assert lifespan._arm_deadline(0) is None
