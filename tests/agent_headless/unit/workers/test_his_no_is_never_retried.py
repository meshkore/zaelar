"""His «no» to the act a task asked about is the task's decision, never a shortfall to retry (V2-857, live 2026-11-06).

«mándale un whatsapp a Raquel…» → the worker asked (it had read the inbox) → «no, no lo mandes» → nothing was sent,
and then the circuit read the goal «the message appears as sent» as UNMET and relaunched a worker that set out to send
it again and asked again. His no is recorded on the row (`worker_api_answer._declined`) and `circuit.close` reads it
as a decision: the task ends `skipped`, no relaunch.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


@pytest.fixture
def row(monkeypatch):
    from nucleo.circuit import ledger
    store = {}
    fake = SimpleNamespace(artifact_put=lambda uid, slot, v: store.__setitem__((uid, slot), v),
                           artifact_get=lambda uid, slot: store.get((uid, slot)))
    monkeypatch.setattr(ledger, "store", lambda: fake)
    return store


@pytest.mark.parametrize("no", ["no, no lo mandes", "no, don't send it"])
def test_his_no_to_a_retained_send_is_recorded_on_the_row(row, monkeypatch, no):
    from nucleo.cli import worker_api  # noqa: F401 — the package first
    from nucleo.cli import worker_api_answer as wa
    monkeypatch.setattr(wa, "_says_yes", lambda q, t: False)
    wa._declined("row-1", {"action": "widget_data", "payload": {"action": "send_to"}})
    from nucleo import circuit
    assert circuit.declined("row-1")["action"] == "send_to"


def _rec(**kw):
    return SimpleNamespace(uid="row-1", task_id="t1", status="done", handoff="", goal="send it", kind="generic",
                           done_when={"widget": "mensajeria", "collection": "sent", "where": {"body~": "x"}},
                           trace_id="", sheet="", surface="", depth=0, relay_gen=0, goal_retried=False,
                           result_summary="", ok=True, verdict="", **kw)


def test_a_declined_task_is_skipped_never_relaunched(row, monkeypatch):
    from nucleo import circuit
    from nucleo.acts import errand
    launched = []
    monkeypatch.setattr(errand, "escalate_to_slowbrain", lambda *a, **k: launched.append(a) or 1)
    monkeypatch.setattr(circuit, "verdict_of", lambda rec, now=None: ("unmet", "nothing in sent"))
    row[("row-1", circuit.DECLINED_SLOT)] = {"action": "send_to"}
    assert circuit._close(_rec(), 3) == "skipped" and not launched
    row.clear()                                                     # disarm: no record of his no → it is retried
    circuit._close(_rec(), 3)
    assert launched, "without his recorded no the unmet goal relaunches — the measured bug"
