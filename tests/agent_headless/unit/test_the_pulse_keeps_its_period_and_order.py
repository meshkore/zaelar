"""The pulse keeps its period and its order after the split into `nucleo/pulse/` (refactor2710-10 T-01).

`loop.py` became one class over three parts (workers, flows, due). A split is only a move if one beat still runs the
same steps in the same order, ends with its `loop.tick` signal, and the loop still sleeps `tick_s` (1 s by default)
between beats. Each part is read here through the loop the server mounts, never on its own.

Disarm: swap two awaits in `OrchestratorLoop.tick` → the first test names the order; sleep anything but `tick_s` in
`_run` → the second does.
"""
from __future__ import annotations

import asyncio

from nucleo.pulse import loop as nloop

ORDER = ["_supervise_workers", "_supervise_confirms", "_supervise_harness", "_supervise_errands",
         "_supervise_stale_flows", "_fire_due", "_report_wake", "_maybe_spark", "_maybe_consolidate",
         "_close_idle_session"]


def _recording_loop(monkeypatch, calls: list):
    lp = nloop.OrchestratorLoop()
    for name in ORDER:
        if name == "_close_idle_session":
            monkeypatch.setattr(lp, name, lambda: calls.append("_close_idle_session"))
        else:
            async def step(now, _n=name):
                calls.append(_n)
            monkeypatch.setattr(lp, name, step)
    monkeypatch.setattr(nloop, "_emit", lambda topic, payload=None: calls.append(topic))
    return lp


def test_one_beat_runs_every_step_in_order_and_then_signals(monkeypatch):
    calls: list = []
    lp = _recording_loop(monkeypatch, calls)
    asyncio.run(lp.tick())
    assert calls == ORDER + ["loop.tick"], calls


def test_the_loop_sleeps_its_period_between_beats(monkeypatch):
    monkeypatch.delenv("ZAELAR_LOOP_TICK_SECS", raising=False)
    calls: list = []
    lp = _recording_loop(monkeypatch, calls)
    assert lp.tick_s == 1.0
    slept: list = []

    async def fake_sleep(s):
        slept.append(s)
        if len(slept) == 2:
            lp._stop = True

    monkeypatch.setattr(nloop.asyncio, "sleep", fake_sleep)
    asyncio.run(lp._run())
    assert slept == [1.0, 1.0] and calls.count("loop.tick") == 2
