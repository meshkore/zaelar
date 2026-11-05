"""V2-851 F1a §3 — a task that waits is STATE on its row, and a restart keeps it waiting (CRIT-E19).

On the frozen code `state=waiting` was never written: the pulse skipped its beat for a worker parked on his answer
(`pulse/workers.py`), so the row read `running` while the operator was the one being waited for; and a restart
BURIED the task — «the question died with the process» — because the question lived only in RAM. Now the row says
what it waits for, since when and the question; the beat writes it; the orphan sweep leaves it alone; a restart keeps
it waiting with its ask (the session is resumed by id when he answers, F1b).
"""
from __future__ import annotations

import asyncio
import time

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import tasks_store as ts
from nucleo.circuit import ledger as T

DAY = 86400


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()
    mememb.reset()


def _put(uid, state="running"):
    now = int(time.time())
    ts.task_put({"id": uid, "goal": "send Raquel the photos", "state": state, "created_at": now - 600,
                 "started_at": now - 600})


# ── the row ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_task_that_waits_for_his_answer_says_so_on_its_row(fresh_db):
    _put("ab12cd-1")
    assert T.waiting("ab12cd-1", "user_answer", ask_id="q1", ask="Which Raquel?", now=1000.0)
    row = ts.task_get("ab12cd-1")
    assert (row["state"], row["waiting_for"], row["waiting_since"], row["ask_id"], row["ask"]) == (
        "waiting", "user_answer", 1000, "q1", "Which Raquel?")
    assert row["deadline"] == 1000 + 7 * DAY, "the default wait is the rule's seven days"


def test_a_beat_that_rewrites_the_wait_keeps_its_clock(fresh_db):
    _put("ab12cd-2")
    T.waiting("ab12cd-2", "user_answer", ask_id="q1", ask="Which Raquel?", now=1000.0)
    T.waiting("ab12cd-2", "user_answer", ask="Which Raquel?", now=5000.0)
    assert ts.task_get("ab12cd-2")["waiting_since"] == 1000
    T.waiting("ab12cd-2", "user_answer", ask_id="q2", ask="And which photos?", now=6000.0)
    assert ts.task_get("ab12cd-2")["waiting_since"] == 6000, "a NEW question starts its own clock"


def test_what_a_task_can_wait_for_is_closed_and_an_ending_is_never_reopened(fresh_db):
    _put("ab12cd-3")
    assert not T.waiting("ab12cd-3", "a reply maybe")
    assert T.waiting("ab12cd-3", "event:mail.inbound")
    from nucleo import circuit
    circuit.settle(row="ab12cd-3", state="cancelled")
    assert not T.waiting("ab12cd-3", "user_answer") and ts.task_get("ab12cd-3")["state"] == "cancelled"


def test_an_answer_resumes_the_row_and_keeps_the_question_on_record(fresh_db):
    _put("ab12cd-4")
    T.waiting("ab12cd-4", "user_answer", ask_id="q1", ask="Which Raquel?")
    T.resumed("ab12cd-4")
    row = ts.task_get("ab12cd-4")
    assert (row["state"], row["waiting_for"], row["ask_id"]) == ("running", "", "q1")


# ── the pulse ────────────────────────────────────────────────────────────────────────────────────────────────
def _pulse_over(monkeypatch, sessions):
    from nucleo import dispatch
    from nucleo.pulse.loop import OrchestratorLoop
    monkeypatch.setattr(dispatch, "sync_state", lambda: None)
    monkeypatch.setattr(dispatch, "active_sessions", lambda: sessions)
    monkeypatch.setattr(dispatch, "unclosed_uids", lambda: {s["uid"] for s in sessions})

    async def _noop(*a, **k):
        return None
    asyncio.run(OrchestratorLoop(deliver=_noop)._supervise_workers(time.time()))


def test_the_beat_writes_the_wait_of_a_worker_parked_on_his_answer(fresh_db, monkeypatch):
    """The skipped beat (`pulse/workers.py`) is what left the row `running` while he was the one being waited for."""
    _put("ab12cd-5")
    _pulse_over(monkeypatch, [{"id": "5", "uid": "ab12cd-5", "status": "running", "waiting_on": "user",
                               "ask": "Which Raquel?", "age_s": 30, "phase": "asking"}])
    row = ts.task_get("ab12cd-5")
    assert (row["state"], row["waiting_for"], row["ask"]) == ("waiting", "user_answer", "Which Raquel?")


def test_the_orphan_sweep_leaves_a_waiting_task_alone(fresh_db):
    """Nobody carries a task that waits for him — on purpose. Its deadline ends it, never the sweep."""
    _put("abcdef-6")                                         # a previous boot's row
    T.waiting("abcdef-6", "user_answer", ask="Which Raquel?")
    assert T.reconciled(set()) == 0
    assert ts.task_get("abcdef-6")["state"] == "waiting"


# ── the restart ──────────────────────────────────────────────────────────────────────────────────────────────
def test_a_restart_keeps_a_waiting_task_waiting_with_its_question(fresh_db, monkeypatch):
    from nucleo.pulse import rehydrate as R
    _put("abcdef-7")
    T.waiting("abcdef-7", "user_answer", ask_id="q7", ask="¿Qué Raquel?", now=time.time() - 120)
    since = ts.task_get("abcdef-7")["waiting_since"]
    R.remember([{"id": "7", "uid": "abcdef-7", "goal": "manda las fotos a Raquel", "kind": "generic",
                 "status": "running", "waiting_on": "user", "ask": "¿Qué Raquel?"}])
    plan = R.at_boot(schedule=False)
    assert plan["buried"] == [] and plan["resume"] == [] and [e["uid"] for e in plan["waiting"]] == ["abcdef-7"]
    row = ts.task_get("abcdef-7")
    assert (row["state"], row["ask_id"], row["ask"], row["waiting_since"]) == ("waiting", "q7", "¿Qué Raquel?", since)
