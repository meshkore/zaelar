"""A task row says each move on the timeline (`task_progress`), so a replay rebuilds where the task stood.

Only its ENDING was an event (`task_state`, at settle); the plan its worker reported, the question it waits on, a worker
that died, the name that arrived — all of it was written into the row and nowhere else. Every door that moves a row now
emits ONE `task_progress` event with what it changed (a delta), its writer named; a birth or an open carries the whole
row and its harness (the end state the circuit judges it by). A move that changed nothing emits nothing, every text is
bounded, and an emit that fails never changes how the task goes.
"""
from __future__ import annotations

import time

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import circuit
from nucleo.circuit import ledger, progress, spec
from voice import observer

END = {"widget": "agenda", "collection": "meetings", "where": {"title~": "Dentist"}}


@pytest.fixture
def moves(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    spec.reset()
    got: list = []
    real = observer.emit

    def emit(kind, label, text="", role="", extra=None):
        ours = str((extra or {}).get("task_id") or "")       # this file's rows only: a pool thread of an earlier
        if kind == progress.KIND and (ours.startswith("p-") or ours == ledger.task_uid(7)):   # test may still land
            got.append({"label": label, "text": text, **(extra or {})})
        return real(kind, label, text=text, role=role, extra=extra)
    monkeypatch.setattr(observer, "emit", emit)
    yield got
    spec.reset()
    memdb.reset_db()


def _live(uid: str, **kw) -> dict:
    return {"uid": uid, "phase": "", "plan": [], "done": 0, "total": 0, "pct": 0, "note": "", "waiting_on": "",
            "ask": "", "backend": "", "heartbeat_at": int(time.time()), "reported_at": 0, **kw}


def test_a_birth_carries_the_whole_row(moves):
    uid = ledger.born(7, "book the dentist for Thursday", {"trace": "T1·aa", "origin": "voz"})
    mine = [m for m in moves if m["task_id"] == uid]     # another test's pool thread may still be landing its own
    assert [m["writer"] for m in mine] == ["born"], moves
    m = mine[0]
    assert m["task_id"] == uid and m["snapshot"] is True and m["trace"] == "T1·aa"
    assert m["delta"]["goal"] == "book the dentist for Thursday" and m["state"] == ledger.STARTING
    ledger.born(7, "book the dentist for Thursday")          # the same birth again changed nothing
    assert len([m for m in moves if m["task_id"] == uid]) == 1, moves


def test_each_status_write_says_what_changed_and_a_beat_that_changed_nothing_is_silent(moves):
    ts.task_put({"id": "p-1", "goal": "find a flat in Lisbon", "state": "running", "created_at": int(time.time())})
    plan = ["search the portals", "read the listings", "shortlist three"]
    ledger.status_written(_live("p-1", phase="reading listings", plan=plan, done=2, total=3, note="12 seen, 4 kept"))
    assert [m["writer"] for m in moves] == ["status_written"], moves
    d = moves[-1]["delta"]
    assert d["phase"] == "reading listings"
    assert d["progress"]["plan"] == plan and d["progress"]["resolved"] == plan[:2], d
    assert "heartbeat_at" not in d and "12 seen" in moves[-1]["text"]
    ledger.status_written(_live("p-1", phase="reading listings", plan=plan, done=2, total=3, note="12 seen, 4 kept",
                                heartbeat_at=int(time.time()) + 15))
    assert len(moves) == 1, moves                                # only its clocks moved: nothing to tell


def test_a_wait_its_resume_a_new_name_and_the_ending_are_each_one_move(moves):
    ts.task_put({"id": "p-2", "goal": "write to Raquel", "state": "running", "created_at": int(time.time()),
                 "trace_id": "T2·bb"})
    ledger.status_written(_live("p-2", waiting_on="user", ask="By WhatsApp or by email?"))
    wait = [m for m in moves if m["writer"] == "waiting"]
    assert wait and wait[-1]["state"] == "waiting", moves
    assert wait[-1]["delta"]["waiting_for"] == ledger.USER_ANSWER and wait[-1]["delta"]["ask"].startswith("By WhatsApp")
    ledger.resumed("p-2")
    assert moves[-1]["writer"] == "resumed" and moves[-1]["state"] == "running"

    class Rec:
        uid, title = "p-2", "Message to Raquel"
    ledger.retitled(Rec())
    assert moves[-1]["writer"] == "retitled" and moves[-1]["delta"] == {"title": "Message to Raquel"}
    circuit.settle(row="p-2", state="done", outcome="sent by WhatsApp")
    end = moves[-1]
    assert end["writer"] == "settle" and end["state"] == "done" and end["delta"]["outcome"] == "sent by WhatsApp"
    assert end["trace"] == "T2·bb"


def test_the_harness_rides_with_the_open_and_with_its_end_state(moves):
    ts.task_put({"id": "p-3", "goal": "book the dentist", "state": "running", "created_at": int(time.time())})
    spec.open(END, text="book the dentist", source="worker", task_id="p-3", now=time.time())
    h = [m for m in moves if m["writer"] == "spec"]
    assert h and "Dentist" in h[-1]["harness"]["end_state"] and h[-1]["harness"]["status"] == "started", moves
    circuit.settle(row="p-3", state="failed", outcome="no slot")
    assert moves[-1]["writer"] == "settle" and moves[-1]["harness"]["end_state"], moves[-1]


def test_texts_and_plans_are_bounded(moves):
    ts.task_put({"id": "p-4", "goal": "x", "state": "running", "created_at": int(time.time())})
    ledger.status_written(_live("p-4", note="n" * 5000, plan=[f"step {i}" for i in range(40)], done=30, total=40))
    p = moves[-1]["delta"]["progress"]
    assert len(p["note"]) <= progress.TEXT_CAP
    assert len(p["plan"]) <= progress.LIST_CAP and len(p["resolved"]) <= progress.LIST_CAP


def test_an_emit_that_fails_never_changes_how_the_task_goes(moves, monkeypatch):
    ts.task_put({"id": "p-5", "goal": "x", "state": "running", "created_at": int(time.time())})

    def boom(*a, **k):
        raise RuntimeError("timeline down")
    monkeypatch.setattr(observer, "emit", boom)
    ledger.status_written(_live("p-5", phase="working"))
    circuit.settle(row="p-5", state="done", outcome="ok")
    row = ts.task_get("p-5")
    assert row["phase"] == "working" and row["state"] == "done"

