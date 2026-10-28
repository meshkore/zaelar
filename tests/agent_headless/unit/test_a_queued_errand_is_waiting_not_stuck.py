"""A queued errand is WAITING, not stuck — and it says behind what (demo 2026-10-22).

Two Brain Workers run at a time. The trip plan sat «queued» four minutes behind a 14-minute monitor search and the
Bitcoin summary; the loop's silence clock ran from its creation, fired `worker.stuck` at 180 s, the agent told him it
was stuck, and «restarting» it only cancelled the one in the queue.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from nucleo import dispatch

from nucleo.dispatch import session as dispatch_session
from nucleo.workers import reports


def test_a_commission_that_waits_names_what_it_waits_behind(monkeypatch):
    said: list = []
    monkeypatch.setattr(reports, "session_phase", lambda tid, phase: said.append((tid, phase)))
    monkeypatch.setattr(dispatch, "active_sessions", lambda: [
        {"id": "1", "status": "running", "title": "Find three 27-inch 4K monitors"},
        {"id": "2", "status": "running", "title": "One-page Bitcoin summary"},
        {"id": "3", "status": "queued", "title": "Plan a 5-day trip"}])

    async def run():
        monkeypatch.setattr(dispatch, "_sem", asyncio.Semaphore(1))
        await dispatch._pool().acquire()                        # the slots are taken
        dispatch_session._say_queued_behind(dispatch, "3")
        dispatch._pool().release()
        dispatch_session._say_queued_behind(dispatch, "3")      # a free slot: nothing to say
    asyncio.run(run())
    assert len(said) == 1 and said[0][0] == "3"
    assert "monitors" in said[0][1] and "Bitcoin" in said[0][1] and "trip" not in said[0][1]


def test_the_loop_does_not_call_a_queued_errand_stuck(monkeypatch):
    from nucleo import loop as _loop
    stuck: list = []
    monkeypatch.setattr(_loop, "_emit", lambda topic, payload: stuck.append(topic) if topic == "worker.stuck" else None)
    rows = [{"id": "3", "status": "queued", "kind": "generic", "age_s": 400, "silent_s": 400, "backend": "x"}]
    monkeypatch.setattr(dispatch, "active_sessions", lambda: rows)
    lp = _loop.OrchestratorLoop()
    asyncio.run(lp._supervise_workers(__import__("time").time()))
    assert not stuck, "a commission waiting for a slot was declared stuck"
    rows[0]["status"] = "running"                               # the same silence, RUNNING, is stuck
    asyncio.run(lp._supervise_workers(__import__("time").time()))
    assert stuck == ["worker.stuck"]
