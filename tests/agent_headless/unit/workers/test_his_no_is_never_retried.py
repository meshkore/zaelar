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


# ── the wiring (audit 2026-11-06 H1): his answer goes through `answer()` and ONE reader decides yes / no / neither ──
@pytest.fixture
def asked(row, monkeypatch):
    """A retained send waiting on his answer; the judge is off (None), the act and the resume are recorded, not run."""
    from nucleo.cli import worker_api as m
    from nucleo.cli import worker_api_answer as wa
    from widgets import confirm as wc
    ran, declined = [], []
    monkeypatch.setattr(wc, "_judge", lambda q, r, timeout=4.0: None)
    monkeypatch.setattr(wa, "_declined", lambda uid, ret: declined.append(uid))
    monkeypatch.setattr(wa, "_keep", lambda uid, e: None)
    monkeypatch.setattr(wa, "_record_for", lambda e: None)
    monkeypatch.setattr(m, "_exec_allow", lambda a, p, rec: ran.append(a) or asyncio.sleep(0, {"ok": True}))
    monkeypatch.setattr(m, "_clear_waiting", lambda *a: None)
    from nucleo.circuit import ledger
    monkeypatch.setattr(ledger, "resumed", lambda uid: None, raising=False)
    from nucleo.workers import task_files
    monkeypatch.setattr(task_files, "record", lambda *a: None)
    monkeypatch.setattr(task_files, "said", lambda *a: None)

    def say(text, choice=None):
        ran.clear(), declined.clear()
        m._ACTS["c1"] = {"uid": "row-1", "task_id": "t1", "question": "¿Se lo mando a Raquel?", "state": "pending",
                         "retained": {"action": "widget_data", "payload": {"action": "send_to"}}}
        asyncio.run(wa.answer("c1", text, resume=False, choice=choice))
        return ("ran" if ran else "declined" if declined else "neither")
    yield say
    m._ACTS.pop("c1", None)


@pytest.mark.parametrize("text, want", [
    ("no", "declined"), ("no, no lo mandes", "declined"),
    ("sí, mándalo, no tardes", "neither"),      # a «no» inside a yes is not his no (it was, and it killed the task)
    ("yes, send it, no rush", "neither"),
    ("espera, ¿a cuál Raquel?", "neither"),     # a question back is not a decision
])
def test_only_a_no_read_as_a_no_ends_the_task(asked, text, want):
    assert asked(text) == want


def test_a_correction_is_never_recorded_as_his_no(asked):
    assert asked("vale, pero mañana") != "declined"


def test_the_bound_pick_of_the_declared_answers_decides(asked):
    assert asked("lo que sea", choice=1) == "declined"
    assert asked("lo que sea", choice=0) != "declined"
