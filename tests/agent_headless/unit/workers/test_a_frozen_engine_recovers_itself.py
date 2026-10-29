"""A frozen engine recovers itself (V2-831 T-28, engine half).

A 2 GB host ran out of memory; the event loop stopped answering and nothing acted — every supervisor ran on that loop.
`nucleo/pulse/self_watchdog.py` is a THREAD: it beats the loop and reads free memory; unhealthy, it sheds (an event,
admission held, the last-started worker paused); still unhealthy after `stuck_s` and under a supervisor, it exits
through the server's graceful shutdown with a non-zero status (ended hard after `exit_grace_s`). Unsupervised it never
exits. Thresholds are declared beside the worker envelope's.
"""
from __future__ import annotations

import asyncio
import inspect
import threading
import time

import pytest

from nucleo.pulse import self_watchdog as wd

POL = {"freeze_s": 15.0, "stuck_s": 120.0, "exit_grace_s": 15.0}


@pytest.mark.parametrize("age,pressure,since,now,can_exit,want", [
    (1, False, 0, 100, True, "ok"),
    (20, False, 0, 100, True, "shed"),            # the loop has not answered for longer than freeze_s
    (1, True, 0, 100, True, "shed"),              # free memory under the envelope's floor
    (20, False, 50, 100, True, "shed"),           # unhealthy, but not for stuck_s yet
    (20, False, 50, 171, True, "exit"),
    (20, False, 50, 171, False, "shed"),          # unsupervised: it never exits
    (1, False, 50, 171, True, "recovered"),
])
def test_one_reading_decides(age, pressure, since, now, can_exit, want):
    assert wd.decide(now, age, pressure, since, POL, can_exit) == want


class _Frozen:
    """A loop that never runs what is posted to it."""
    def call_soon_threadsafe(self, *a, **k):
        return None


@pytest.fixture
def world(monkeypatch):
    from nucleo.workers import envelope
    from nucleo import dispatch
    acts = {"events": [], "shed": [], "relieve": 0, "hook": 0, "timers": []}
    monkeypatch.setattr(wd, "policy", lambda: dict(POL))
    monkeypatch.setattr(envelope, "measured", lambda: (2000, 1000))
    monkeypatch.setattr(envelope, "shed", lambda s: acts["shed"].append(s))
    monkeypatch.setattr(envelope, "relieve", lambda recs: acts.__setitem__("relieve", acts["relieve"] + 1) or "")
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    monkeypatch.setattr(wd, "_emit", lambda label, **x: acts["events"].append((label, x)))

    class _Timer:
        def __init__(self, s, fn):
            acts["timers"].append(s)
            self.daemon = True
        def start(self):
            return None
    monkeypatch.setattr(wd.threading, "Timer", _Timer)
    monkeypatch.setitem(wd._exit_hook, "fn", lambda: acts.__setitem__("hook", acts["hook"] + 1))
    monkeypatch.setattr(wd, "_state", {"beat": 0.0, "since": 0.0, "shed": False, "exiting": False, "code": 0,
                                       "thread": None, "stop": None})
    return acts


def test_a_frozen_loop_sheds_then_exits_under_a_supervisor(world, monkeypatch):
    monkeypatch.setenv("ZAELAR_SUPERVISED", "1")
    wd._state["beat"] = 1000.0                                  # the last beat the loop answered
    assert wd.tick(_Frozen(), now=1020.0) == "shed"
    assert wd.tick(_Frozen(), now=1060.0) == "shed"
    assert len(world["events"]) == 1, "one event per episode, not per reading"
    assert world["shed"] and world["relieve"] == 2
    assert wd.tick(_Frozen(), now=1141.0) == "exit"
    assert world["hook"] == 1 and world["timers"] == [POL["exit_grace_s"]] and wd.exit_code() == wd.EXIT_CODE
    assert wd.tick(_Frozen(), now=1200.0) == "shed", "asked once: the exit is not asked again"


def test_unsupervised_it_sheds_and_never_exits(world, monkeypatch):
    monkeypatch.delenv("ZAELAR_SUPERVISED", raising=False)
    wd._state["beat"] = 1000.0
    for now in (1020.0, 1200.0, 5000.0):
        assert wd.tick(_Frozen(), now=now) == "shed"
    assert world["hook"] == 0 and wd.exit_code() == 0


def test_memory_pressure_alone_sheds(world, monkeypatch):
    from nucleo.workers import envelope
    monkeypatch.setattr(envelope, "measured", lambda: (2000, 100))     # 5 % free, under the 10 % floor
    wd._state["beat"] = time.monotonic()
    assert wd.tick(_Frozen(), now=time.monotonic()) == "shed"


def test_a_loop_that_answers_is_healthy_and_an_episode_closes(world):
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    try:
        wd._state.update(beat=time.monotonic(), since=time.monotonic() - 30, shed=True)   # an open episode
        assert wd.tick(loop) == "recovered" and wd._state["since"] == 0.0
        assert any("recupera" in label for label, _ in world["events"])
        time.sleep(0.05)                                           # the loop runs the beat it was posted
        assert wd.tick(loop) == "ok" and time.monotonic() - wd._state["beat"] < 1.0, "the beat is the loop's answer"
    finally:
        loop.call_soon_threadsafe(loop.stop)
        t.join(1)
        loop.close()


def test_it_is_wired_into_boot_shutdown_and_the_exit_status():
    import importlib
    lifespan = importlib.import_module("server.lifespan")
    from server.boot import surfaces
    import server.__main__ as _m  # noqa: F401 — import only, its body runs under __main__
    assert "self_watchdog.start()" in inspect.getsource(surfaces)
    assert "nucleo.pulse.self_watchdog" in inspect.getsource(lifespan)
    src = open(_m.__file__, encoding="utf-8").read()
    assert "_self_watchdog.request_exit(" in src and "sys.exit(_self_watchdog.exit_code())" in src


def test_the_thresholds_are_declared_data():
    import json
    from pathlib import Path
    d = json.loads((Path(wd.__file__).resolve().parents[2] / "config" / "resources.default.json").read_text())
    assert {"freeze_s", "stuck_s", "exit_grace_s"} <= set(d)
