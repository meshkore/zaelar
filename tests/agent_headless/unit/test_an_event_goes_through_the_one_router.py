"""An event goes through the ONE router (V2-851 F4, §7): what arrives without a turn is a request with its origin,
routed by `flow_of.route(event=…)` — a task WAITING for it resumes, a CLAIMANT (an errand bound to the conversation)
takes it, a rule SUBSCRIBED to it hands it to the stream worker, else nothing. A subscription is a rules row matched
in code on the event's declared fields; his note is read into one once; a pre-condition is a declared verdict. The
stream is ONE recurring row per stream that rests between items, obeys ⏻, carries the rules' mandate, and recycles
its session after `RECYCLE_EVENTS`. Disarm: with no subscription read (`rows` → []), the mail that the rule names
routes to nothing (`test_disarmed_no_subscription_routes_nothing`).
"""
from __future__ import annotations

import asyncio
import time

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo import events
from nucleo.circuit import ledger
from nucleo.events import pump, stream
from nucleo.turn import flow_events, flow_of

ADDR = "billing@acme.example"
RULE_TEXT = f"When an email from {ADDR} arrives, add a task to my agenda to pay the invoice."
SHAPED = ('{"topic": "mail.in", "match": {"sender": "%s"}, "do": "add a task to pay the invoice", '
          '"may": ["agenda"], "if": ""}' % ADDR)


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


def _mail(sender: str = ADDR) -> dict:
    return events.of_message({"platform": "email", "senderId": sender, "chatId": sender, "senderName": "ACME",
                              "subject": "Invoice", "body": "Your November invoice: $91.10", "messageId": "m1"})


def _subscribe(chat=lambda s, u: SHAPED) -> str:
    import rules
    from rules import subscriptions
    note = rules.add("widget:mensajeria", "pref", "note", RULE_TEXT, text=RULE_TEXT)
    subscriptions.shape_notes(chat=chat)
    return note["id"]


def test_his_note_is_read_once_into_a_subscription_row():
    import rules
    from rules import subscriptions
    calls = []
    nid = _subscribe(chat=lambda s, u: calls.append(u) or SHAPED)
    rows = subscriptions.rows(events.MAIL_IN)
    assert [r["id"] for r in rows] == [f"{nid}~ev"] and rows[0]["value"]["match"] == {"sender": ADDR}
    assert subscriptions.shape_notes(chat=lambda s, u: calls.append(u) or SHAPED) == 0 and len(calls) == 1
    rules.remove(nid)
    assert subscriptions.rows(events.MAIL_IN) == [], "removing the rule he said removes what it subscribed"


def test_a_note_that_is_no_subscription_is_read_once_and_left():
    from rules import subscriptions
    _subscribe(chat=lambda s, u: '{"topic": ""}')
    assert subscriptions.rows(events.MAIL_IN) == [] and subscriptions.unread_notes() == []


def test_a_subscribed_mail_goes_to_the_stream_and_another_sender_to_nothing():
    _subscribe()
    assert flow_events.route(_mail())["as"] == flow_events.STREAM
    assert flow_events.route(_mail("someone@else.example"))["as"] == flow_events.NOTHING


def test_disarmed_no_subscription_routes_nothing(monkeypatch):
    from rules import subscriptions
    _subscribe()
    monkeypatch.setattr(subscriptions, "rows", lambda topic: [])
    assert flow_events.route(_mail())["as"] == flow_events.NOTHING


def test_a_precondition_is_a_declared_verdict(monkeypatch):
    from rules import subscriptions
    _subscribe(chat=lambda s, u: SHAPED.replace('"if": ""', '"if": "it is not advertising"'))
    asked = []

    def _jev(state, q, question_id=""):
        asked.append(question_id)
        return {subscriptions.PRECONDITION: {"choice": "no", "confidence": 0.9}, "_ready_at": time.time()}

    import nucleo.jev as jev
    monkeypatch.setattr(jev, "choose_many_sync", _jev)
    monkeypatch.setattr(jev, "read", lambda h, k, fb, min_confidence=0.5: ((h or {}).get(k) or {}).get("choice", fb)
                        and (h[k]["choice"], h[k]))
    assert flow_events.route(_mail())["as"] == flow_events.NOTHING and asked == [subscriptions.PRECONDITION]


def test_a_task_waiting_for_the_event_resumes_before_any_rule():
    _subscribe()
    ts = ledger.store()
    now = int(time.time())
    ts.task_put({"id": "b0-1", "goal": "wait for the invoice", "state": "running", "created_at": now})
    ledger.waiting("b0-1", events.waits_for(events.MAIL_IN, f"email:{ADDR}"))
    r = flow_events.route(_mail())
    assert r["as"] == flow_events.RESUME and r["by"] == "row" and r["task"] == "b0-1"


def test_a_claimant_takes_what_is_its_own():
    flow_events.claimant(events.MAIL_IN, "errand", lambda ev: {"row": {"id": "e1"}} if ev["key"].endswith(ADDR) else None)
    r = flow_events.route(_mail())
    assert r["as"] == flow_events.RESUME and r["by"] == "errand" and r["claim"]["row"]["id"] == "e1"


def test_the_router_is_flow_of_route():
    _subscribe()
    assert asyncio.run(flow_of.route(event=_mail()))["as"] == flow_events.STREAM


def test_the_stream_is_one_recurring_row_that_rests_and_carries_the_mandate(monkeypatch):
    launched = []
    from nucleo.acts import errand
    monkeypatch.setattr(errand, "escalate_to_slowbrain", lambda text, context=None: launched.append(context) or 7)
    _subscribe()
    r = asyncio.run(pump.publish(_mail()))
    assert r["as"] == flow_events.STREAM and len(launched) == 1
    row = ledger.store().task_get("stream-mail")
    assert row["mode"] == "recurring" and row["kind"] == "stream" and row["origin"] == "event"
    ctx = launched[0]
    assert ctx["task_uid"] == "stream-mail" and ctx["mandate"]["may"] == ["schedule"] and "resume" not in ctx   # the one grant vocabulary (V2-857)
    asyncio.run(pump.publish(_mail()))
    assert len(launched) == 1, "one item at a time: the second waits for the stream to rest"
    ledger.store().task_patch("stream-mail", session_id="sess-1")
    from nucleo import circuit
    circuit.settle(row="stream-mail", state="done", outcome="task added")
    row = ledger.store().task_get("stream-mail")
    assert row["state"] == "waiting" and row["waiting_for"] == events.waits_for(events.MAIL_IN)
    assert stream.drain() == 1 and launched[1]["resume"]["native_sid"] == "sess-1", "the SAME session resumes"


def test_the_stream_recycles_its_session_and_obeys_the_switch(monkeypatch):
    launched = []
    from nucleo import runstate
    from nucleo.acts import errand
    monkeypatch.setattr(errand, "escalate_to_slowbrain", lambda text, context=None: launched.append(context) or 7)
    _subscribe()
    row = stream.ensure_row("mail", events.MAIL_IN)
    ledger.store().task_patch(row["id"], session_id="sess-1", progress={"events": stream.RECYCLE_EVENTS})
    monkeypatch.setattr(runstate, "stopped", lambda: True)
    asyncio.run(pump.publish(_mail()))
    assert launched == [], "⏻ off: the item is held, like a cron"
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    assert stream.drain() == 1 and "resume" not in launched[0], "past RECYCLE_EVENTS a fresh session starts"
