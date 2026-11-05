"""V2-852 T11 seam · A row that ends says so on the bus, once (`task.ended`), so what it leaves behind can close.

The cancelled task's empty card stayed on screen: nothing told the card's owner that its row had ended. The circuit's
one writer of an ending publishes `task.ended` {task_id, state, trace} beside its `task_state` event; a subscriber
(a bus sink) closes what the row owned — the circuit imports none of them.
"""
from __future__ import annotations

import time

import pytest

import bus
from memory import db as memdb
from memory import tasks_store as ts
from nucleo import circuit


@pytest.fixture
def ended(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    got: list = []

    def sink(ev):
        if isinstance(ev, dict) and ev.get("topic") == "task.ended":
            got.append(ev.get("payload"))
    bus.add_sink(sink)
    yield got
    bus.remove_sink(sink)
    memdb.reset_db()


@pytest.mark.parametrize("state", ["cancelled", "done", "failed"])
def test_a_row_that_ends_publishes_task_ended_once(ended, state):
    ts.task_put({"id": "e11-1", "goal": "plan a weekend in Porto", "state": "running", "created_at": int(time.time()),
                 "trace_id": "T4·ab12"})
    circuit.settle(row="e11-1", state=state, outcome="x")
    circuit.settle(row="e11-1", state=state, outcome="x again")          # no move: nothing new to tell
    assert ended == [{"task_id": "e11-1", "state": state, "trace": "T4·ab12"}], ended
