"""V2-851 §3b / CRIT-C7 — every row ends through `circuit.settle`, and says so once: `task_state` names the writer.

The static half (no other function writes an ending) is node 7.91. This is the running half: each door that used to
write its own ending — a worker's close, an early end, a delivery at the first rung, the pulse's orphan sweep, a cut
by a restart, the list runner, the errand and schedule mirrors — now moves the row through `settle`, and the row's
move into its ending is ONE `task_state` event with `writer: settle`. CRIT-C7's door test is here too: a transactional
op (a send, a delete) is no commission — its row never reaches the board, and only `settle` ends it.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import circuit
from nucleo.circuit import ledger as T


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


@pytest.fixture(autouse=True)
def _no_turn_left_behind():
    """`begin` sets the turn on a ContextVar of the test's own context: put back what was there, or the next file's
    turn reads these words as its own."""
    from nucleo.request import model as request_row
    token = request_row._TURN.set(None)
    yield
    request_row._TURN.reset(token)


@pytest.fixture
def states(monkeypatch):
    """Every `task_state` event the product emits, as its payload."""
    from voice import observer
    seen: list[dict] = []
    real = observer.emit

    def _emit(kind, *a, **k):
        if kind == "task_state":
            seen.append(dict(k.get("extra") or {}))
            return None
        return real(kind, *a, **k)
    monkeypatch.setattr(observer, "emit", _emit)
    return seen


def _of(seen, uid):
    return [(e["state"], e["writer"]) for e in seen if e.get("task_id") == uid]


def _put(uid, state="running", **kw):
    now = int(time.time())
    ts.task_put({"id": uid, "goal": "x", "state": state, "created_at": now - 600, "started_at": now - 600, **kw})


# ── CRIT-C7: a transactional op is no commission ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("widget,action,words", [
    ("mensajeria", "send_draft", "send Raquel the photos"),
    ("lista", "remove_item", "borra la leche de la lista"),
])
def test_a_send_or_a_delete_leaves_no_board_row_and_only_settle_ends_it(fresh_db, states, widget, action, words):
    from nucleo.request import model as request_row
    request_row.begin(words)
    uid = request_row.opened(widget, action)
    assert uid and ts.task_get(uid)["state"] == "running", "the op opened no row — this test would prove nothing"
    circuit.settle(row=uid, verdict="met")
    board = T.board("live") + T.board("done")
    assert all(r["id"] != uid for r in board), "a transactional op reached his task list"
    assert ts.task_get(uid)["state"] == "done"
    assert _of(states, uid) == [("done", "settle")]


# ── each former writer, through settle ──────────────────────────────────────────────────────────────────────
def test_a_worker_ending_is_settled_once(fresh_db, states, monkeypatch):
    monkeypatch.setattr(T, "remembered", lambda *a, **k: None)
    rec = SimpleNamespace(uid="c0ffee-1", status="done", waiting_on="", settled="", result_summary="found 3",
                          error_class="", verdict="met", sheet="", title="t", goal="g", kind="web")
    _put(rec.uid)
    T.closed(rec)
    T.closed(rec)                                       # a second close of an ended row says nothing new
    assert ts.task_get(rec.uid)["state"] == "done" and ts.task_get(rec.uid)["verdict"] == "met"
    assert _of(states, rec.uid) == [("done", "settle")]


def test_a_live_worker_close_writes_no_ending(fresh_db, states):
    rec = SimpleNamespace(uid="c0ffee-2", status="relevada", waiting_on="", settled="")
    _put(rec.uid)
    T.closed(rec)
    assert ts.task_get(rec.uid)["state"] == "running" and _of(states, rec.uid) == []


@pytest.mark.parametrize("state", ["failed", "cancelled"])
def test_an_early_end_is_settled(fresh_db, states, state):
    rec = SimpleNamespace(uid=f"c0ffee-3{state[0]}", result_summary="no provider")
    _put(rec.uid, state="pending")
    T.ended_early(rec, state=state)
    assert _of(states, rec.uid) == [(state, "settle")]


def test_a_first_rung_delivery_is_settled(fresh_db, states):
    uid = T.born(7, "a picture of a cat", {})
    T.first_rung_delivered(uid, 3)
    assert ts.task_get(uid)["state"] == "done" and _of(states, uid) == [("done", "settle")]


def test_the_orphan_sweep_and_a_restart_cut_are_settled(fresh_db, states):
    boot = T._boot_id()
    _put(f"{boot}-4")
    _put("abcdef-2")
    assert T.reconciled(set()) == 2
    T.interrupted({"id": "9", "uid": "fedcba-9", "goal": "a hotel in Rome", "why": "cut"})
    assert _of(states, f"{boot}-4") == [("failed", "settle")]
    assert _of(states, "abcdef-2") == [("failed", "settle")]
    assert _of(states, "fedcba-9") == [("failed", "settle")]


def test_a_mirror_ends_through_settle_once_and_is_never_rewound(fresh_db, states):
    errand = {"id": "e1", "objective": "book a table", "state": "closed", "closed_at": int(time.time()),
              "outcome": "booked for 21:00", "created_at": int(time.time()) - 60}
    T.errand_mirrored({**errand, "state": "contacting"})
    T.errand_mirrored(errand)
    T.errand_mirrored(errand)                           # the mirror is re-written; the ending is said once
    assert ts.task_get("errand:e1")["state"] == "done"
    assert _of(states, "errand:e1") == [("done", "settle")]
    job = {"id": 5, "status": "fired", "updated": int(time.time()), "detail": {"schedule": {"type": "once"}}}
    T.scheduled_mirrored(job)
    T.scheduled_mirrored(job)
    assert _of(states, "cron:5") == [("done", "settle")]


def test_an_upsert_never_rewinds_an_ended_row(fresh_db):
    _put("c0ffee-9")
    circuit.settle(row="c0ffee-9", state="cancelled")
    _put("c0ffee-9", state="running")
    row = ts.task_get("c0ffee-9")
    assert row["state"] == "cancelled" and row["finished_at"]


def test_settle_refuses_what_is_not_an_ending(fresh_db, states):
    _put("c0ffee-8")
    circuit.settle(row="c0ffee-8", state="running")
    circuit.settle(row="c0ffee-8", verdict="started")
    assert ts.task_get("c0ffee-8")["state"] == "running" and _of(states, "c0ffee-8") == []
