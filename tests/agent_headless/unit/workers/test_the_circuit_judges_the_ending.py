"""V2-776 L3 · A worker's ending is JUDGED by the circuit, with one explicit bound and one honest report (node 3.105).

`workers/goal.py` retried «once» on a flag every relay rebuilt (the real cap was `relay_gen < 2`, shared with
the context and provider relays), ended on the worker's `ok` when the condition was unreadable, and spoke
nothing about it. Now the bound is `genesis.circuit.retries`, its count lives on the spec (persisted on the
task row), unreadable is a verdict of its own, a gave-up ending parks ONE retry on the operator's answer,
and the pulse re-verifies every open spec.
"""
from __future__ import annotations

import pytest

from memory import db as memdb
from nucleo import circuit, spec
from nucleo import tasks as T

GONE = {"all": [{"widget": "agenda", "collection": "meetings", "where": {"title~": "Cryptonite"}, "expect": "absent"}]}
THERE = {"all": [{"widget": "agenda", "collection": "meetings", "where": {"title~": "Cryptonite"}}]}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db()
    memdb.get_db()
    spec.reset()
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path / "w"))
    from widgets.agenda import data as agenda, gcal
    monkeypatch.setattr(gcal, "svc", lambda: None)
    db = agenda.load_db()
    db["meetings"] = [{"id": "m1", "title": "Cryptonite call", "date": "2026-10-02", "startTime": "10:00", "endTime": "10:30"}]
    store.save(agenda.WIDGET_ID, db)
    yield
    spec.reset()
    memdb.reset_db()


def _rec(**kw):
    from nucleo.workers.session import SessionRecord
    r = SessionRecord(task_id="t1", goal="cancela la cita con Cryptonite y avísale")
    r.ok = True
    r.result_summary = "Listo, cancelada y avisado."
    for k, v in kw.items():
        setattr(r, k, v)
    return r


def _stub(monkeypatch):
    escalations: list = []
    parked: list = []
    from nucleo.flash import escalate as esc
    from nucleo import dispatch_confirm as dc
    monkeypatch.setattr(esc, "escalate_to_slowbrain", lambda req, context=None: escalations.append((req, context or {})) or 1)
    monkeypatch.setattr(dc, "remember_offer", lambda request, *, context, question: parked.append((request, context, question)))
    return escalations, parked


def test_an_unmet_ending_is_relaunched_carrying_what_is_missing(world, monkeypatch):
    esc, parked = _stub(monkeypatch)
    rec = _rec(done_when=GONE)
    assert circuit.close(rec, relay_cap=2) == "retrying"
    req, ctx = esc[0]
    assert "[ARNÉS]" in req and "Cryptonite" in req and ctx["done_when"] == GONE and ctx["relay_gen"] == 1
    assert rec.ok is False and rec.result_summary == "" and rec.handoff and rec.verdict == "retrying"
    assert parked == []


def test_the_bound_is_the_operators_and_the_count_lives_on_the_spec(world, monkeypatch):
    esc, parked = _stub(monkeypatch)
    monkeypatch.setattr(circuit, "settings", lambda: {"retries": 1, "ask_on_give_up": True})
    rec = _rec(done_when=GONE)
    T.opened(rec, {"src": "voice"})                       # the spec is born on the row, tries = 0
    assert circuit.close(rec, relay_cap=5) == "retrying"
    assert spec.of_task(rec.uid)["tries"] == 1
    rec2 = _rec(done_when=GONE, relay_gen=1, uid=rec.uid, goal_retried=False)
    assert circuit.close(rec2, relay_cap=5) == "gave_up", "retries=1 means one relaunch, then the truth"
    assert len(esc) == 1
    assert rec2.ok is False and "Queda:" in rec2.result_summary and "Listo, cancelada" in rec2.result_summary


def test_a_gave_up_ending_parks_one_retry_on_his_answer_and_only_one(world, monkeypatch):
    esc, parked = _stub(monkeypatch)
    monkeypatch.setattr(circuit, "settings", lambda: {"retries": 0, "ask_on_give_up": True})
    rec = _rec(done_when=GONE)
    T.opened(rec, {"src": "voice"})
    assert circuit.close(rec, relay_cap=5) == "gave_up"
    assert len(parked) == 1 and "Cryptonite" in parked[0][2] and parked[0][1]["done_when"] == GONE
    assert circuit.RETRY_QUESTION in rec.result_summary
    assert spec.of_task(rec.uid)["status"] == "gave_up"
    rec2 = _rec(done_when=GONE, uid=rec.uid)
    circuit.close(rec2, relay_cap=5)
    assert len(parked) == 1, "the same clause failing again asks nothing more — once is the bound"


def test_a_met_ending_is_delivered_untouched(world, monkeypatch):
    esc, parked = _stub(monkeypatch)
    rec = _rec(done_when=THERE)
    assert circuit.close(rec, relay_cap=2) == "met"
    assert esc == [] and parked == [] and rec.ok is True and rec.result_summary == "Listo, cancelada y avisado."


def test_undeclared_changes_nothing_and_unreadable_is_its_own_verdict(world, monkeypatch):
    esc, parked = _stub(monkeypatch)
    rec = _rec()
    assert circuit.close(rec, relay_cap=2) == "undeclared" and rec.ok is True
    rec = _rec(done_when={"all": [{"widget": "agenda", "collection": "facturas"}]})
    assert circuit.close(rec, relay_cap=2) == "unverifiable"
    assert esc == [] and rec.ok is True, "None is «cannot be read», never «failed» — and never a retry"
    rec = _rec(spec_unverifiable=True)
    assert circuit.close(rec, relay_cap=2) == "unverifiable"


def test_a_cancelled_or_relieved_ending_is_not_judged(world, monkeypatch):
    esc, parked = _stub(monkeypatch)
    assert circuit.close(_rec(done_when=GONE, status="cancelled"), relay_cap=2) == "skipped"
    assert circuit.close(_rec(done_when=GONE, handoff="context"), relay_cap=2) == "skipped"
    assert esc == [] and parked == []


def test_the_pulse_re_verifies_open_specs_and_closes_the_met_ones(world):
    e = spec.open(THERE, text="x", source="test")
    assert circuit.tick(now=1000.0) and e["status"] == "met"
    e2 = spec.open(GONE, text="y", source="test")
    assert circuit.tick(now=1001.0) == [] and e2["status"] == "open" and e2["last"] is False
    e2["last"] = None
    assert circuit.tick(now=1002.0) == [] and e2["last"] is None, "an open spec is read at most every 5 s"


def test_the_bound_comes_from_genesis_with_a_default():
    assert isinstance(circuit.retries(), int) and circuit.retries() >= 0
    import json, pathlib
    g = json.loads((pathlib.Path(circuit.__file__).parent / "genesis.json").read_text(encoding="utf-8"))
    assert "circuit" in g and int(g["circuit"]["retries"]) == 2
