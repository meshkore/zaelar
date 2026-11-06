"""V2-851 F1e — a worker process that dies WITHOUT finishing, with a resumable session id, is not failed: its row waits
for the worker (`waiting_for=worker`), keeping its phase, and the pulse resumes it by id ONCE (bounded by `attempts`);
a second death fails it with its reason. Without a session id it ends as before.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import tasks_store as ts
from nucleo.circuit import ledger
from nucleo.workers import session as _session  # noqa: F401 — the session module imports its finish half
from nucleo.workers import session_finish


@pytest.fixture
def row(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    now = int(time.time())
    ts.task_put({"id": "b0-9", "goal": "hotel in Valencia", "title": "Hotel", "state": "running",
                 "session_id": "sess-1", "created_at": now, "started_at": now})
    yield "b0-9"
    memdb.reset_db()
    mememb.reset()


def _rec(**kw):
    base = dict(task_id="9", uid="b0-9", native_sid="sess-1", status="running", result_seen=False, error_class="",
                provider_down=None, context_full=None, handoff="", perm_denied="", phase="reading booking.com")
    return SimpleNamespace(**{**base, **kw})


def test_a_death_is_told_apart_from_an_ending(row):
    assert session_finish.died(_rec())
    for kw in ({"result_seen": True}, {"status": "cancelled"}, {"native_sid": ""}, {"error_class": "stalled"},
               {"handoff": "relay"}, {"context_full": {"t": 1}}):
        assert not session_finish.died(_rec(**kw)), kw


def test_the_first_death_waits_for_the_worker_keeping_its_place(row):
    now = time.time()
    assert ledger.worker_died(_rec(), now=now)
    r = ts.task_get(row)
    assert (r["state"], r["waiting_for"], r["phase"], r["attempts"]) == ("waiting", "worker", "reading booking.com", 1)
    assert r["deadline"] == int(now + ledger.WORKER_RESUME_AFTER_S)
    assert ledger.worker_resumes_due(now + 1) == [], "it is resumed after its pause, never in a tight loop"
    assert [x["id"] for x in ledger.worker_resumes_due(now + ledger.WORKER_RESUME_AFTER_S + 1)] == [row]
    assert ts.task_get(row)["state"] == "running" and not ts.task_get(row)["waiting_for"]


def test_a_second_death_is_not_resumed(row):
    ledger.worker_died(_rec())
    ledger.resumed(row)
    assert not ledger.worker_died(_rec()), "bounded by `attempts`: the ending fails it, with its reason"


def test_the_row_without_a_session_id_is_not_kept(row):
    ts.task_patch(row, session_id="")
    assert not ledger.worker_died(_rec(native_sid=""))
