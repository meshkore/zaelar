"""ONE vocabulary for how a request ended (refactor2710-02 T-00, `nucleo/circuit/verdict.py`).

Five tables named the same endings, each with its own values: the circuit's seven, the inline row's four-value rank,
the spec/harness status, the repair pass's outcomes and a shape read from our own reply. A row the circuit closed
`gave_up` ranked like `met` because the rank table did not know the word, and memory decided «delivered» by the
position of a value in a tuple. Each verdict now declares what every reader needs from it, once.

Disarm: make `verdict.keeps` always False → the rank test goes red; drop the emit from `request_row.settle` → the
event test goes red.
"""
from __future__ import annotations

import pytest

from nucleo.circuit import verdict as V


def test_the_eight_values_and_what_each_declares():
    assert set(V.ALL) == {"started", "met", "unmet", "unverifiable", "undeclared", "cannot", "asked", "skipped"}
    assert {n for n, v in V.ALL.items() if v.delivered} == {"met", "undeclared", "unverifiable"}
    assert {n for n, v in V.ALL.items() if v.ending} == {"met", "unmet", "unverifiable", "undeclared", "cannot"}
    for v in V.ALL.values():
        assert v.row_state in ("running", "waiting", "done", "failed", "cancelled"), v
        assert v.label, v
        assert (v.rank is None) == (not v.ending), v


def test_the_repair_pass_names_its_two_verdicts_as_the_vocabulary_does():
    from nucleo.turn import promise_kept
    assert V.of(promise_kept.CANNOT) is V.CANNOT and V.of(promise_kept.STARTED) is V.STARTED


def test_the_names_older_rows_carry_read_as_the_one_vocabulary():
    assert V.of("gave_up") is V.UNMET and V.of("retrying") is V.STARTED and V.of("open") is V.STARTED
    assert V.of("") is None and V.of("whatever") is None
    assert V.from_attest(True) is V.MET and V.from_attest(False) is V.UNMET and V.from_attest(None) is V.UNVERIFIABLE


@pytest.mark.parametrize("prev,new,kept", [
    ("unmet", "met", True), ("unverifiable", "met", True), ("cannot", "unmet", True), ("gave_up", "met", True),
    ("met", "unmet", False), ("met", "met", False), ("", "met", False), ("started", "met", False),
])
def test_a_later_op_never_improves_a_failed_row(prev, new, kept):
    assert V.keeps(prev, new) is kept


@pytest.fixture
def rows(monkeypatch):
    store: dict = {}

    class _TS:
        def task_get(self, uid):
            return store.get(uid)

        def task_patch(self, uid, **f):
            store[uid].update(f)

    from nucleo.circuit import ledger as tasks
    monkeypatch.setattr(tasks, "store", lambda: _TS())
    return store


def test_a_settle_writes_the_declared_state_and_emits_with_the_rows_trace(rows, monkeypatch):
    from nucleo.request import model as request_row
    from voice import observer
    seen: list = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None: seen.append(
        {"kind": kind, "label": label, **(extra or {})}))
    rows["r1"] = {"id": "r1", "verdict": "", "trace_id": "t-row", "outcome": "agenda:add"}
    request_row.settle("r1", "unverifiable", "agenda:add")
    assert rows["r1"]["state"] == "done" and rows["r1"]["verdict"] == "unverifiable"
    got = [e for e in seen if e["kind"] == "verdict"]
    assert got and got[0]["verdict"] == "unverifiable" and got[0]["trace"] == "t-row" and got[0]["uid"] == "r1"


def test_a_non_ending_is_never_settled(rows):
    from nucleo.request import model as request_row
    rows["r2"] = {"id": "r2", "verdict": "", "state": "running"}
    for name in ("started", "asked", "skipped", "retrying", "nonsense"):
        request_row.settle("r2", name)
    assert rows["r2"] == {"id": "r2", "verdict": "", "state": "running"}


def test_memory_keeps_a_result_only_when_the_verdict_declares_it_delivered(monkeypatch):
    import asyncio

    from nucleo.memory_agent import writer
    kept: list = []

    async def _remember(p):
        kept.append(p)
    monkeypatch.setattr("nucleo.memory_agent.external.remember", _remember)
    for name in ("met", "undeclared", "unverifiable", "unmet", "gave_up", "cannot", "started"):
        asyncio.run(writer.result("the report", task_id=name, verdict=name))
    assert [p["meta"]["verdict"] for p in kept] == ["met", "undeclared", "unverifiable"]
