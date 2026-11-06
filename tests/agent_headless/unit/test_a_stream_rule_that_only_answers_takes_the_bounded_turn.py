"""A stream rule that only answers takes the BOUNDED turn (V2-857 phase 7, ES/EN): ONE stream task, TWO playbooks,
chosen by what his rules GRANT, never by his words. «cuando me escriba Quinn, dile que estoy de viaje» (`may:
["message"]`) and an arriving message → one model turn with no tools, the engine sends the reply to THAT same chat
through the outbound queue, and no worker session starts; a rule granting `schedule` → the session; a model answer
`needs_hands: true` → the session; an unreadable answer → nothing sent, the row rests `failed`. Disarm: with `fits`
returning False the answering rule takes the session (`test_disarmed_the_answering_rule_takes_the_session`).
The model call and the outbound queue are monkeypatched; nothing touches real state.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo import events
from nucleo.circuit import ledger
from nucleo.events import pump, stream, stream_reply
from nucleo.turn import flow_events

QUINN = "34600111222@s.whatsapp.net"
CASES = {
    "es": {"rule": "cuando me escriba Quinn, dile que estoy de viaje", "do": "dile que estoy de viaje",
           "body": "¿Quedamos el jueves?", "reply": "Ahora mismo está de viaje, te escribirá a la vuelta."},
    "en": {"rule": "when Quinn writes to me, tell her I'm travelling", "do": "tell her I'm travelling",
           "body": "Shall we meet on Thursday?", "reply": "He's travelling right now and will write back on return."},
}


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    import rules
    rules._reset_for_tests()
    monkeypatch.setattr(flow_events, "_CLAIMANTS", {})
    monkeypatch.setattr(stream, "_QUEUE", {})
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    yield
    rules._reset_for_tests()
    memdb.reset_db()
    mememb.reset()


@pytest.fixture
def world(monkeypatch):
    """The two outside doors, recorded: the worker session (`escalate_to_slowbrain`) and the outbound queue."""
    sessions, sent = [], []
    from connectors.messaging import store as msgstore
    from nucleo.acts import errand
    from widgets.mensajeria import outbound
    monkeypatch.setattr(errand, "escalate_to_slowbrain", lambda text, context=None: sessions.append(context) or 7)
    monkeypatch.setattr(msgstore, "load", lambda: {})
    monkeypatch.setattr(msgstore, "save", lambda db: None)
    monkeypatch.setattr(outbound, "enqueue", lambda db, target, text, **kw: sent.append((target, text)) or "q1")
    return {"sessions": sessions, "sent": sent}


def _model(monkeypatch, answer: str) -> list:
    from nucleo.errands import wake
    asked = []

    async def _ask(system, dossier, **kw):
        asked.append(dossier)
        return answer
    monkeypatch.setattr(wake, "_ask_model", _ask)
    return asked


def _subscribe(lang: str, may: list[str]) -> None:
    import rules
    from rules import subscriptions
    c = CASES[lang]
    rules.add("widget:mensajeria", "pref", "note", c["rule"], text=c["rule"])
    shaped = json.dumps({"topic": events.CONNECTOR_MSG, "match": {"sender": QUINN}, "do": c["do"], "may": may,
                         "if": ""})
    subscriptions.shape_notes(chat=lambda s, u: shaped)


def _arrive(lang: str) -> dict:
    msg = {"platform": "whatsapp", "senderId": QUINN, "chatId": QUINN, "senderName": "Quinn",
           "body": CASES[lang]["body"], "messageId": "w1"}

    async def _go():
        r = await pump.publish(events.of_message(msg))
        await asyncio.gather(*list(stream_reply._RUNNING))
        return r
    return asyncio.run(_go())


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_rule_that_only_answers_replies_to_the_same_chat_without_a_session(monkeypatch, world, lang):
    asked = _model(monkeypatch, json.dumps({"reply": CASES[lang]["reply"], "needs_hands": False, "why": "his rule"}))
    _subscribe(lang, ["message"])
    assert _arrive(lang)["as"] == flow_events.STREAM
    assert world["sessions"] == [], "a rule that only answers starts no worker session"
    assert len(asked) == 1 and CASES[lang]["body"] in asked[0] and "untrusted" in asked[0]
    assert [(t["platform"], t["chatId"], text) for t, text in world["sent"]] == \
        [("whatsapp", QUINN, CASES[lang]["reply"])], "the engine sends to the conversation the item came from"
    row = ledger.store().task_get("stream-messages")
    assert row["state"] == "waiting" and row["outcome"].startswith("done: sent")


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_rule_that_grants_schedule_takes_the_session(monkeypatch, world, lang):
    asked = _model(monkeypatch, "{}")
    _subscribe(lang, ["schedule"])
    _arrive(lang)
    assert len(world["sessions"]) == 1 and world["sessions"][0]["mandate"]["may"] == ["schedule"]
    assert asked == [] and world["sent"] == []


@pytest.mark.parametrize("lang", ["es", "en"])
def test_an_answer_that_needs_hands_goes_to_the_session(monkeypatch, world, lang):
    _model(monkeypatch, json.dumps({"reply": "", "needs_hands": True, "why": "a booking"}))
    _subscribe(lang, ["message"])
    _arrive(lang)
    assert len(world["sessions"]) == 1 and world["sessions"][0]["task_uid"] == "stream-messages"
    assert world["sent"] == [], "a reply that needs hands is never improvised in the bounded turn"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_an_unreadable_answer_sends_nothing_and_the_row_rests_failed(monkeypatch, world, lang):
    _model(monkeypatch, "sorry, I cannot")
    _subscribe(lang, ["message"])
    _arrive(lang)
    assert world["sent"] == [] and world["sessions"] == []
    row = ledger.store().task_get("stream-messages")
    assert row["state"] == "waiting" and row["outcome"].startswith("failed:")


@pytest.mark.parametrize("lang", ["es", "en"])
def test_disarmed_the_answering_rule_takes_the_session(monkeypatch, world, lang):
    asked = _model(monkeypatch, json.dumps({"reply": CASES[lang]["reply"], "needs_hands": False, "why": ""}))
    monkeypatch.setattr(stream_reply, "fits", lambda mandate, fields: False)
    _subscribe(lang, ["message"])
    _arrive(lang)
    assert len(world["sessions"]) == 1 and asked == [] and world["sent"] == []
