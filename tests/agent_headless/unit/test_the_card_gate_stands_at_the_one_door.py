"""CRIT-C4 at its door (V2-851 F4): building or rewriting a card of his asks first at `dispatch._run_session`, the one
door a worker is lit — whatever decides that the errand is card code.

Written BEFORE `nucleo/request/kind.py` lost its regexes (the file that was the criterion's only support): the
commission carries the brief's `errand_kind` verdict, so this holds with the old reader and the new one. The door
parks the question and starts no worker; an errand that is not card code passes the gate. Disarm: drop the gate and
a worker starts (`test_disarmed_the_door_lets_a_worker_start`).
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import dispatch
from nucleo.dispatch import confirm as _dconf
from nucleo.workers.session_record import SessionRecord

COMMISSION = ("Modificar el widget `youtube` del operador en dos cosas concretas: rediseñar el HEADER de la tarjeta "
              "para que quede más bonito y limpio")
SURE = 0.95


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    dispatch._PENDING_CONFIRM.clear()
    dispatch._EXPIRED_CONFIRM.clear()
    monkeypatch.setattr(dispatch, "_deliver_confirm", lambda rec: asyncio.sleep(0))
    monkeypatch.setattr(dispatch, "_task_row", lambda *a, **k: None)
    monkeypatch.setattr(dispatch, "sync_state", lambda *a, **k: None)
    yield
    dispatch._PENDING_CONFIRM.clear()
    dispatch._EXPIRED_CONFIRM.clear()


def _run(req: str, verdict: str, monkeypatch) -> dict:
    """Run the door; `passed` is True when the errand went beyond the card gate (towards a worker)."""
    seen = {"passed": False}

    async def _beyond(task, key, req_):
        seen["passed"] = True
        return True                       # stop here: what lies beyond is not this test's

    monkeypatch.setattr(_dconf, "unlicensed_gate", _beyond)
    task = dispatch.Task(id="c4", request=req, kind="generic", trusted=True,
                         context={"errand_kind": {"choice": verdict, "confidence": SURE},
                                  "errand_class": {"choice": "none", "confidence": SURE}})
    dispatch._SESSIONS["c4"] = SessionRecord(task_id="c4", goal=req[:200], kind="generic")
    try:
        asyncio.run(dispatch._run_session(task))
    finally:
        dispatch._SESSIONS.pop("c4", None)
    return seen


def test_rewriting_a_card_of_his_parks_the_question_and_starts_no_worker(monkeypatch):
    seen = _run(COMMISSION, "change_card", monkeypatch)
    assert not seen["passed"], "a card of his was going to be rewritten without asking"
    p = dispatch.pending_confirm()
    assert p and p["task_id"] == "c4" and p["code_change"] == "modify" and p["question"]


def test_an_errand_that_is_not_card_code_passes_the_gate(monkeypatch):
    seen = _run("búscame vuelos a Roma para el jueves", "generic", monkeypatch)
    assert seen["passed"] and not dispatch.pending_confirm()
