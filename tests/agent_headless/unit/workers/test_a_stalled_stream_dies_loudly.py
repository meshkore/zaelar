"""V2-645 — the stall watchdog: a worker whose provider stream dies must END, loudly, not wait forever.

Measured live (the La Mella session, 2026-09-09): the backend's model call hung (TCP closed, 0% CPU, zero
events) and `run()` sat in the event loop indefinitely — no error, no death notice, «sigo con ello» on top.
The watchdog bounds the wait for the NEXT backend event; past it the worker is stopped and `_finish()` runs
the existing death machinery, so the state line can say the truth.
"""
import asyncio

import pytest

from nucleo.workers import session as sess_mod
from nucleo.workers.session import SessionRecord, WorkerSession


class _HangingBackend:
    """One real event, then a stream that never speaks again — the measured failure shape."""
    name = "fake"
    alive = True

    def __init__(self):
        self.stopped = False

    async def start(self, prompt, *, spec):
        pass

    async def send(self, text):
        pass

    async def events(self):
        yield type("E", (), {"type": "phase", "data": {"label": "arrancando"}})()
        await asyncio.sleep(3600)                     # the hung provider call

    async def stop(self, *, grace: float = 3.0):
        self.stopped = True
        self.alive = False


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_a_hung_stream_ends_the_session_with_an_honest_summary(monkeypatch):
    monkeypatch.setattr(sess_mod, "_STALL_S", 0.2)
    b = _HangingBackend()
    rec = SessionRecord(task_id="t1", goal="revisa el grupo del viaje", kind="generic")
    s = WorkerSession(b, type("S", (), {"model": "", "kind": "generic"})(), rec)
    # Bounded from the OUTSIDE so a disarmed watchdog is a counted red, never a hung harness
    # (a failure that kills the instrument is worse than the same failure reported).
    _run(asyncio.wait_for(s.run("da igual"), timeout=5))
    assert rec.status == "error" and rec.ok is False
    assert "dejó de responder" in (rec.result_summary or ""), \
        "the record must carry the truth the state line will speak"
    assert b.stopped, "the hung process is stopped, never left as a zombie"


def test_a_stream_that_finishes_in_time_is_untouched(monkeypatch):
    monkeypatch.setattr(sess_mod, "_STALL_S", 5.0)

    class _Quick(_HangingBackend):
        async def events(self):
            yield type("E", (), {"type": "phase", "data": {"label": "trabajando"}})()
            yield type("E", (), {"type": "done", "data": {"ok": True}})()

    b = _Quick()
    rec = SessionRecord(task_id="t2", goal="tarea corta", kind="generic")
    s = WorkerSession(b, type("S", (), {"model": "", "kind": "generic"})(), rec)
    _run(s.run("da igual"))
    assert rec.status != "error"
    assert "dejó de responder" not in (rec.result_summary or "")


def test_zero_disables_the_watchdog(monkeypatch):
    """`0` must mean OFF (the documented contract), not an instant timeout."""
    monkeypatch.setattr(sess_mod, "_STALL_S", 0.0)

    class _SlowButAlive(_HangingBackend):
        async def events(self):
            await asyncio.sleep(0.4)                  # longer than any accidental tiny timeout
            yield type("E", (), {"type": "done", "data": {"ok": True}})()

    b = _SlowButAlive()
    rec = SessionRecord(task_id="t3", goal="tarea lenta", kind="generic")
    s = WorkerSession(b, type("S", (), {"model": "", "kind": "generic"})(), rec)
    _run(s.run("da igual"))
    assert rec.status != "error"
    assert "dejó de responder" not in (rec.result_summary or "")
