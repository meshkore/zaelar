"""V2-852 T07 (backend) · The cancel button of a running process ends THAT row (his rule R2).

A task runs until it is done or he stops it; from the screen, his stop is the cancel button on its line of the process
list. `POST /api/tasks/<row id>/cancel` → every live worker of that row is told to stop, the row ends `cancelled`
through `circuit.settle` (one `task_state` event, writer named), one line is said through the out-of-turn mouth, and
the answer is `{ok, task_id, state}`. A row with no live worker (a wait on his answer) ends too; an unknown row is 404;
a row that already ended is 409 and nothing is said.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import dispatch


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    events, stopped, said = [], [], []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None:
                        events.append({"kind": kind, **(extra or {})}))
    monkeypatch.setattr(dispatch, "cancel_session", lambda tid, **k: stopped.append((tid, k)) or True)
    from nucleo.pulse import notices

    async def notify(title, text, **kw):
        said.append((text, kw.get("task_id")))
        return {"id": 1, "state": "spoken", "channel": "voice", "duplicate": False}
    monkeypatch.setattr(notices, "notify", notify)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from server import tasks_api
    app = FastAPI()
    app.include_router(tasks_api.router)
    yield SimpleNamespace(c=TestClient(app), events=events, stopped=stopped, said=said)
    memdb.reset_db()


def _row(uid: str, state: str, title: str) -> None:
    ts.task_put({"id": uid, "goal": title, "title": title, "state": state, "created_at": int(time.time())})


def test_the_button_stops_the_worker_and_settles_the_row_once(world, monkeypatch):
    _row("c7-1", "running", "Find a flat to rent in Lisbon")
    rec = SimpleNamespace(uid="c7-1", status="running", task_id="4")
    monkeypatch.setitem(dispatch._SESSIONS, "4", rec)
    r = world.c.post("/api/tasks/c7-1/cancel")
    assert (r.status_code, r.json()) == (200, {"ok": True, "task_id": "c7-1", "state": "cancelled"})
    assert [t for t, _ in world.stopped] == ["4"] and rec.status == "cancelled", "its worker was not told to stop"
    assert ts.task_get("c7-1")["state"] == "cancelled"
    moves = [e for e in world.events if e["kind"] == "task_state" and e.get("task_id") == "c7-1"]
    assert len(moves) == 1 and moves[0]["writer"] == "settle", moves
    assert len(world.said) == 1 and world.said[0][1] == "c7-1" and "Lisbon" in world.said[0][0]


def test_a_row_waiting_on_his_answer_with_no_live_worker_ends_too(world):
    _row("c7-2", "waiting", "Book a table for four")
    r = world.c.post("/api/tasks/c7-2/cancel")
    assert r.status_code == 200 and r.json()["state"] == "cancelled" and world.stopped == []


def test_an_unknown_row_is_404_and_an_ended_one_409_with_nothing_said(world):
    assert world.c.post("/api/tasks/nope-9/cancel").status_code == 404
    _row("c7-3", "done", "Compare two phone plans")
    r = world.c.post("/api/tasks/c7-3/cancel")
    assert (r.status_code, r.json()) == (409, {"ok": False, "task_id": "c7-3", "state": "done"})
    assert world.said == [] and ts.task_get("c7-3")["state"] == "done"


def test_a_session_id_from_the_phone_names_its_row(world, monkeypatch):
    _row("c7-4", "running", "Track a parcel from Porto")
    monkeypatch.setitem(dispatch._SESSIONS, "6", SimpleNamespace(uid="c7-4", status="running", task_id="6"))
    r = world.c.post("/api/tasks/6/cancel")
    assert (r.status_code, r.json()) == (200, {"ok": True, "task_id": "c7-4", "state": "cancelled"})
    assert ts.task_get("c7-4")["state"] == "cancelled" and [t for t, _ in world.stopped] == ["6"]
