"""The ⏻ ON gesture revives a dead heartbeat (V2-516).

Measured 2026-08-31: a syntax-broken instant of `nucleo/loop.py` (a translation pass rewriting the file
at the moment the engine imported it) made the lifespan's one-shot `loop.start()` fail with a warning.
The engine stayed up with NO pulse — crons silent, the orb's ECG flat — and the operator's ⏻, the one
gesture that should fix a stopped state, did nothing: `runstate.start()` only resumed workers.

Two halves, each disarmed separately:
  · `OrchestratorLoop.start()` must not let a DONE task (crashed, or cancelled outside `stop()`) block
    a revive — `is_running()` already reports it dead.
  · `runstate.start()` must check the heartbeat and start it when the brain is nucleo.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import loop as nloop
from nucleo import runstate


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    # …and the HANDLE, because the env var alone does not isolate: `memory/db.py::get_db()` caches a
    # PROCESS-WIDE singleton, so once any earlier test has opened the real database this fixture writes into
    # it. Measured 2026-09-01: `runstate.start("test")` below landed in the operator's own `sys_kv` and left
    # his stopped agent reading RUNNING — the ⏻ is HIS intention (V2-092) and a test may not flip it.
    from memory import db as _memdb
    _memdb.reset_db()
    runstate._reset_for_tests()
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "resume_all", lambda: 0)
    yield
    runstate._reset_for_tests()
    _memdb.reset_db()          # …and give the handle back, so the next test does not inherit this temp one


def test_a_dead_task_does_not_block_a_revive():
    async def scenario():
        lp = nloop.OrchestratorLoop()
        lp._task = asyncio.create_task(asyncio.sleep(0))     # a task that ends on its own (a crash looks the same)
        await asyncio.sleep(0.01)
        assert lp._task.done() and not lp.is_running()
        started = {"n": 0}
        lp._run = lambda: started.__setitem__("n", started["n"] + 1) or asyncio.sleep(3600)  # type: ignore
        lp.start()
        try:
            assert lp.is_running()                            # the revive took
            assert started["n"] == 1
        finally:
            lp._task.cancel()
    asyncio.run(scenario())


def test_power_on_revives_a_dead_heartbeat(isolated, monkeypatch):
    monkeypatch.setenv("ZAELAR_LOOP", "1")
    import config.v2 as _v2
    monkeypatch.setattr(_v2, "active_brain", lambda: "nucleo")
    calls = {"start": 0}
    monkeypatch.setattr(nloop, "is_running", lambda: False)
    monkeypatch.setattr(nloop, "start", lambda: calls.__setitem__("start", calls["start"] + 1))
    res = asyncio.run(runstate.start("test"))
    assert calls["start"] == 1                                # ⏻ ON brought the pulse back
    assert res["ok"] is True


def test_power_on_leaves_a_live_heartbeat_alone(isolated, monkeypatch):
    monkeypatch.setenv("ZAELAR_LOOP", "1")
    import config.v2 as _v2
    monkeypatch.setattr(_v2, "active_brain", lambda: "nucleo")
    calls = {"start": 0}
    monkeypatch.setattr(nloop, "is_running", lambda: True)
    monkeypatch.setattr(nloop, "start", lambda: calls.__setitem__("start", calls["start"] + 1))
    res = asyncio.run(runstate.start("test"))
    assert calls["start"] == 0                                # already beating → untouched
    assert res.get("heartbeat") is True
