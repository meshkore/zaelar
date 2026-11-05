"""A parked errand waits on its OWN row through the one asker (V2-857 P0-1, architecture audit 2026-11-05).

The three start gates (an irreversible act, a card of his to build, a line that was not a request) used to FORGET the
row (`ledger.withdrawn` → `task_forget`) and keep the question only in this process: «pay the bill» → asked → a
restart → his «yes» went to nothing, and «how is it going?» found no task. Now the question is durable on the row
(`dispatch.confirm.make_durable` → `circuit.asker`), the yes relaunches the same request ON THAT ROW, and whichever
reader takes the answer — the in-memory gate or the bound durable ask — the errand starts once.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nucleo.dispatch import confirm as dc


@pytest.fixture
def gate(monkeypatch):
    from nucleo.acts import errand
    from nucleo import circuit
    from nucleo.circuit import asker, ledger
    from nucleo.request import inline_ask
    from nucleo.cli import worker_api  # noqa: F401 — the package first: its answer module imports it back
    from nucleo.cli import worker_api_answer
    asked, launched, settled = [], [], []
    monkeypatch.setattr(asker, "ask", lambda uid, entry, bus_id="": asked.append((uid, entry)) or entry["ask_id"])
    monkeypatch.setattr(errand, "escalate_to_slowbrain", lambda req, context=None: launched.append((req, context)) or 1)
    monkeypatch.setattr(circuit, "settle", lambda **k: settled.append(k))
    monkeypatch.setattr(ledger, "resumed", lambda uid: None)
    monkeypatch.setattr(worker_api_answer, "_says_yes", lambda q, t: t.lower().startswith(("sí", "si", "yes")))
    inline_ask._TAKEN.clear()
    dc._PENDING_CONFIRM.clear()
    task = SimpleNamespace(kind="generic", trusted=True, context={"trace": "T1", "errand_class": "moves_money"})
    dc.remember_confirm("k1", "pay the electricity bill", task)
    rec = SimpleNamespace(uid="row-1", task_id="k1")
    yield SimpleNamespace(rec=rec, asked=asked, launched=launched, settled=settled)
    dc._PENDING_CONFIRM.clear()


def test_the_question_is_durable_on_its_row(gate):
    ask_id = dc.make_durable("k1", gate.rec)
    (uid, entry), = gate.asked
    assert uid == "row-1" and ask_id == entry["ask_id"] and entry["said"] is True
    assert entry["retained"]["kind"] == "start" and entry["retained"]["pending"]["request"] == "pay the electricity bill"


@pytest.mark.parametrize("yes", ["sí, págala", "yes, go ahead"])
def test_his_yes_relaunches_the_same_request_on_that_row(gate, yes):
    dc.make_durable("k1", gate.rec)
    _uid, entry = gate.asked[0]
    assert dc.rerun_start("row-1", entry, yes)["ok"] is True
    (req, ctx), = gate.launched
    assert req == "pay the electricity bill" and ctx["confirmed"] is True and ctx["task_uid"] == "row-1"


def test_after_a_restart_the_row_alone_relaunches_it(gate):
    dc.make_durable("k1", gate.rec)
    _uid, entry = gate.asked[0]
    dc._PENDING_CONFIRM.clear()                                    # the process that asked is gone
    assert dc.rerun_start("row-1", entry, "yes")["ok"] is True
    assert gate.launched and gate.launched[0][1]["task_uid"] == "row-1"


def test_a_no_ends_the_row_and_starts_nothing(gate):
    dc.make_durable("k1", gate.rec)
    _uid, entry = gate.asked[0]
    assert dc.rerun_start("row-1", entry, "no, déjalo")["ok"] is False
    assert not gate.launched and gate.settled[0]["state"] == "cancelled"


def test_two_readers_of_the_yes_start_it_once(gate):
    dc.make_durable("k1", gate.rec)
    _uid, entry = gate.asked[0]
    dc.resolve_confirm(True, "k1")                                 # the in-memory gate took it first
    dc.rerun_start("row-1", entry, "yes")                          # …and the bound durable ask arrives
    assert len(gate.launched) == 1


def test_the_gates_no_longer_forget_the_row():
    import inspect
    from nucleo.dispatch import session
    src = inspect.getsource(session) + inspect.getsource(dc.unlicensed_gate)
    assert '_task_row("withdrawn"' not in src and src.count("make_durable(key, rec)") == 3
