"""V2-851 F1a — the task row is the agent's STATE: what it waits for, how it resumes, and the turn it came from.

The worker could already ask, but nothing durable said so: the question lived in a RAM registry a restart emptied,
and the row's `trace_id` was "" on every inline row and on a worker row whose birth knew no trace — so no flow could
be joined to its task (F0 battery, §15f). These pin the columns, the board that serves them, and the trace.
"""
from __future__ import annotations

import sqlite3
import time

import pytest

from memory import db as memdb
from memory import schema as memschema
from memory import tasks_store as ts
from nucleo.circuit import ledger as T

WAIT_FIELDS = ("session_id", "cwd", "waiting_for", "waiting_since", "deadline", "ask_id", "ask", "playbook")


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield tmp_path / "zaelar.db"
    memdb.reset_db()


@pytest.fixture(autouse=True)
def _no_turn_left_behind():
    """`begin` sets the turn on a ContextVar of the test's own context: put back what was there, or the next file's
    turn reads these words as its own."""
    from nucleo.request import model as request_row
    token = request_row._TURN.set(None)
    yield
    request_row._TURN.reset(token)


def test_a_task_row_has_every_field_of_its_wait(fresh_db):
    cols = {r[1] for r in sqlite3.connect(fresh_db).execute("PRAGMA table_info(tasks)")}
    assert set(WAIT_FIELDS) <= cols, sorted(set(WAIT_FIELDS) - cols)


def test_an_older_database_gains_them_and_a_second_open_changes_nothing(tmp_path, monkeypatch):
    """Idempotent: a v10 file (no wait columns) migrates on open, and opening it again is a no-op."""
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute(memschema.TASKS)
    con.execute("PRAGMA user_version = 10")
    con.commit()
    con.close()
    monkeypatch.setenv("ZAELAR_DB", str(path))
    for _ in range(2):
        memdb.reset_db()
        memdb.get_db()
    memdb.reset_db()
    cols = {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(tasks)")}
    assert set(WAIT_FIELDS) <= cols


def test_the_board_serves_the_wait_of_a_row(fresh_db):
    """GET /api/tasks reads `ledger.board`: a waiting row brings its question even with no live worker behind it."""
    now = int(time.time())
    ts.task_put({"id": "b0a0d0-3", "goal": "send Raquel the photos", "state": "running", "created_at": now})
    ts.task_patch("b0a0d0-3", state="waiting", waiting_for="user_answer", waiting_since=now, ask_id="a1",
                  ask="Which Raquel?", session_id="s-9", cwd="/tmp/w", deadline=now + 60, playbook="message")
    row = next(r for r in T.board("live", show_all=True) if r["id"] == "b0a0d0-3")
    assert {k: row[k] for k in WAIT_FIELDS} == {
        "session_id": "s-9", "cwd": "/tmp/w", "waiting_for": "user_answer", "waiting_since": now,
        "deadline": now + 60, "ask_id": "a1", "ask": "Which Raquel?", "playbook": "message"}


def test_a_later_writer_never_blanks_the_trace_the_birth_wrote(fresh_db):
    """The errand is born in its turn with the trace; the dispatcher's upsert, which may know none, keeps it."""
    uid = T.born(41, "find me a flat", {"trace": "t-born"})
    ts.task_put({"id": uid, "goal": "find me a flat", "state": "pending", "trace_id": ""})
    assert ts.task_get(uid)["trace_id"] == "t-born"


def test_a_worker_row_takes_the_trace_its_escalation_carried(fresh_db):
    from types import SimpleNamespace
    rec = SimpleNamespace(task_id=42, title="", goal="hotel in Rome", kind="web", surface="", sheet="",
                          trace_id="", started=time.time(), status="queued", waiting_on="")
    uid = T.opened(rec, {"trace": "t-esc"})
    assert ts.task_get(uid)["trace_id"] == "t-esc"


def test_an_inline_row_carries_the_trace_of_its_turn(fresh_db):
    """The channel calls `begin(text)` with no trace; the row is joined to the turn the words came in."""
    from nucleo.request import model as request_row
    from voice import trace as vtrace
    with vtrace.scope("t-turn"):
        request_row.begin("delete the milk from my list")
        uid = request_row.opened("lista", "remove_item")
    assert uid and ts.task_get(uid)["trace_id"] == "t-turn"
