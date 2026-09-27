"""V2-776 D2 — the pulse watches the workers: a silent one is ANNOUNCED, then restarted ONCE, then failed honestly.

The operator (2026-09-27): the pulse «se va a encargar de controlar todas las tareas … de vigilarlos y de ver
cuando uno se cuelga para reiniciarlo, de decirle al usuario qué está pasando». Before this the stall watchdog
killed the worker and that was the end of the errand, and the «it went quiet» moment was only an event nobody
heard. The restart count lives in the durable row, because every restart builds a fresh record.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import dispatch
from nucleo import loop as L
from nucleo import tasks as T
from nucleo.workers import relay
from nucleo.workers import stall as stall_mod
from nucleo.workers.session import SessionRecord, WorkerSession
from tests.agent_headless.unit.workers.test_a_stalled_stream_dies_loudly import _HangingBackend, _run


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


@pytest.fixture
def escalations(monkeypatch):
    sent = []
    from nucleo.flash import escalate
    monkeypatch.setattr(escalate, "escalate_to_slowbrain", lambda req, context=None: sent.append((req, context)))
    return sent


def _stalled_rec(uid="abcdef-3", **kw):
    ts.task_put({"id": uid, "goal": "widget de contabilidad", "state": "running", "created_at": int(time.time())})
    rec = SessionRecord(task_id="3", goal="widget de contabilidad", uid=uid, status="error", ok=False, **kw)
    rec.error_class = "stalled"
    return rec


def test_the_first_stall_restarts_the_same_commission(fresh_db, escalations):
    rec = _stalled_rec()
    relay.restart_stalled(rec)
    assert len(escalations) == 1
    _, ctx = escalations[0]
    assert ctx["task_uid"] == "abcdef-3" and ctx["src"] == "stall_restart"
    assert rec.handoff, "a restart is a handoff — the errand is not over, and must not be announced as dead"
    assert ts.task_get("abcdef-3")["attempts"] == 1


def test_the_second_stall_is_the_end(fresh_db, escalations):
    rec = _stalled_rec()
    ts.task_patch("abcdef-3", attempts=1)
    relay.restart_stalled(rec)
    assert escalations == [] and not rec.handoff


def test_a_failure_that_is_not_a_stall_is_not_restarted_here(fresh_db, escalations):
    rec = _stalled_rec()
    rec.error_class = ""
    relay.restart_stalled(rec)
    assert escalations == []


def test_a_hung_stream_goes_through_the_restart(fresh_db, escalations, monkeypatch):
    """The wiring: the real session loop, a real hang, the real `_finish` — not the function alone."""
    monkeypatch.setattr(stall_mod, "_STALL_S", 0.2)
    monkeypatch.setattr(stall_mod, "_TICK_S", 0.05)
    ts.task_put({"id": "abcdef-9", "goal": "g", "state": "running", "created_at": int(time.time())})
    rec = SessionRecord(task_id="9", goal="revisa el grupo del viaje", kind="generic", uid="abcdef-9")
    s = WorkerSession(_HangingBackend(), type("S", (), {"model": "", "kind": "generic"})(), rec)
    _run(asyncio.wait_for(s.run("da igual"), timeout=5))
    assert [c["task_uid"] for _, c in escalations] == ["abcdef-9"]
    assert rec.status == "relevada"


def test_a_failed_row_says_why(fresh_db):
    rec = _stalled_rec()
    T.closed(rec)
    row = ts.task_get("abcdef-3")
    assert row["state"] == "failed" and row["error_class"] == "stalled"


def test_the_pulse_SAYS_a_worker_went_quiet(monkeypatch):
    said = []

    async def _deliver(title, text, **kw):
        said.append((text, kw.get("key")))
    rec = SessionRecord(task_id="5", goal="búscame piso en Gràcia", status="running", backend="widget_generator")
    rec.started = time.time() - dispatch.STUCK_SECS - 30
    rec.last_event_at = time.time() - dispatch.STUCK_SECS - 10
    monkeypatch.setattr(dispatch, "_SESSIONS", {"5": rec})
    loop = L.OrchestratorLoop(deliver=_deliver)
    asyncio.run(loop._supervise_workers(time.time()))
    asyncio.run(loop._supervise_workers(time.time() + 1))     # once, not every second
    stuck = [t for t, k in said if k == L._STUCK_KEY + "5"]
    assert len(stuck) == 1 and "Gràcia" in stuck[0]
