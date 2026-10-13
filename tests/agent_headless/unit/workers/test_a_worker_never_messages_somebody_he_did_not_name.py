"""A worker never messages somebody he did not name: the send becomes a question, and his «yes» sends it.

`best-plumber-same-day__es` (2026-10-14, sandbox 20261014-010939-es): he asked to FIND a well-rated plumber
who can come today. The brief the turn's model wrote said «Buscar y contactar fontaneros», and the worker
called `mensajeria send_to {to: 683139819, text: «Hola, ¿fontaneros de urgencia?…»}` twice. The door ALLOWED
it (`classify_act` → `action_mode_now` → FAST, because `send_to` is `confirm:false` for a turn executing his
order); only a missing directory entry stopped it.
"""
import asyncio
import json
import time

import pytest

from nucleo import his_words, worker_api, worker_policy


class _Rec:
    task_id = "1"
    goal = "Buscar y contactar fontaneros de urgencia en Madrid centro con buenas valoraciones"
    waiting_on = ask = ask_corr = ""

    def __init__(self):
        self.started = time.time()


@pytest.fixture
def door(monkeypatch):
    his_words.reset()
    rec = _Rec()
    ran: list = []

    async def _exec(action, payload, r):
        ran.append((action, payload))
        return {"ok": True}

    monkeypatch.setattr(worker_api, "_verify", lambda tid, tok: rec)
    monkeypatch.setattr(worker_api, "_piggyback", lambda tid: [])
    monkeypatch.setattr(worker_api, "_exec_allow", _exec)
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "get_record", lambda tid: rec)
    worker_api._ACTS.clear()
    yield rec, ran
    worker_api._ACTS.clear()
    his_words.reset()


def _act(payload):
    resp = asyncio.run(worker_api.worker_act(task_id="1", token="x", action="widget_data", payload=payload))
    return json.loads(resp.body)


_SEND = {"widget_id": "mensajeria", "action": "send_to",
         "payload": {"to": "683139819", "text": "Hola, ¿fontaneros de urgencia? Tengo una fuga…",
                     "objective": "Conseguir UN fontanero para HOY"}}


def test_the_premise_the_turn_has_and_the_worker_lacks():
    """The policy alone still allows it — the gate is what changes the answer, not the catalog."""
    assert worker_policy.classify_act("widget_data", _SEND) == worker_policy.ALLOW


def test_a_send_to_a_number_he_never_said_parks_as_a_question(door):
    rec, ran = door
    his_words.note("Tengo una fuga en el baño y necesito un fontanero hoy sí o sí… uno que esté bien valorado")
    his_words.note("Madrid centro")
    out = _act(_SEND)
    assert out.get("status") == "pending" and out.get("corr_id"), out
    assert ran == [], "the message left without his word"
    pend = worker_api.pending_asks()
    assert len(pend) == 1 and "683139819" in pend[0]["question"]
    assert rec.waiting_on == "user", "the turn has to put the question to him"


def test_his_yes_sends_it(door):
    _rec, ran = door
    his_words.note("necesito un fontanero hoy")
    corr = _act(_SEND)["corr_id"]
    assert asyncio.run(worker_api.answer(corr, "sí, escríbele")) is True
    assert ran and ran[0][0] == "widget_data" and ran[0][1]["payload"]["to"] == "683139819"


def test_his_no_sends_nothing(door):
    _rec, ran = door
    corr = _act(_SEND)["corr_id"]
    asyncio.run(worker_api.answer(corr, "no, ya llamo yo"))
    assert ran == []


def test_no_words_on_file_asks(door):
    """A restart, or a channel that never recorded the turn: not knowing what he said is not his yes."""
    _rec, ran = door
    assert _act(_SEND).get("status") == "pending" and ran == []
