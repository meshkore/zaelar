"""The commission gate runs on the text channel too (2026-10-15, live bench E3).

«send the invoice to andrew, tell him we're already trying inworld and he should book it» → the model called
`forward` AND `escalate_to_slowbrain`. The voice annuls that worker (`escalation_guard.settle_commission`: the brief
read `handle_inline`, the turn acted, the reply promised nothing); the text channel launched it beside the send —
a worker free to send the same mail again. One gate, both channels.

Disarm: return `action` unchanged from `probe_after.an_inline_act_settles_the_commission` → red.
"""
from __future__ import annotations

import threading

from nucleo.flash import probe_after


def _brief(escalate: str, conf: float = 0.95) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": ["mensajeria"],
            "result": {"escalate_or_inline": {"choice": escalate, "confidence": conf}}}


def _calls():
    return [{"name": "escalate_to_slowbrain", "args": {"request": "forward the Inworld receipt to Andrew"}},
            {"name": "widget_data", "args": {"widget_id": "mensajeria", "action": "forward",
                                             "payload": {"contact": "Andrew", "text": "book it"}}}]


def test_an_act_on_a_card_read_inline_launches_no_worker_beside_it():
    calls = _calls()
    action = probe_after.an_inline_act_settles_the_commission("escalate", calls, brief=_brief("handle_inline"),
                                                              operator_text="send the invoice to andrew", spoken="Done.")
    assert action == "widget_data"
    assert [t["name"] for t in calls] == ["widget_data"]


def test_a_brief_that_escalates_keeps_the_worker():
    """The same rule the voice runs — an act covers a promise (`reply_promises`), so only the brief keeps a worker."""
    for brief in (_brief("escalate"), _brief("handle_inline", conf=0.3)):
        calls = _calls()
        assert probe_after.an_inline_act_settles_the_commission("escalate", calls, brief=brief, operator_text="x",
                                                                spoken="Done.") == "escalate"
        assert len(calls) == 2


def test_a_worker_alone_is_left_to_the_turn():
    calls = _calls()[:1]
    assert probe_after.an_inline_act_settles_the_commission("escalate", calls, brief=_brief("handle_inline"),
                                                            operator_text="x", spoken="Done.") == "escalate"


def test_the_text_channel_asks_it_before_executing():
    import inspect
    src = inspect.getsource(probe_after.execute_what_was_decided)
    assert "action = an_inline_act_settles_the_commission(action, tool_calls" in src, "the gate is not wired"


def test_a_carried_out_sure_order_settles_a_commission_the_brief_did_not_judge(monkeypatch):
    """Live bench E3: the escalate key missing from the brief, `forward` sure at 0.74 under an order at 1.00 — the act
    the turn ran is the commission. A sure «escalate» (a compound turn) keeps its worker. Shared by both channels."""
    import server.voice_api as _va
    monkeypatch.setattr(_va, "open_instances", lambda: ["mensajeria"])
    b = _brief("handle_inline")
    b["result"] = {"screen_action": {"choice": "mensajeria:forward", "confidence": 0.74},
                   "request_type": {"choice": "order", "confidence": 1.0}}
    calls = _calls()
    assert probe_after.an_inline_act_settles_the_commission("escalate", calls, brief=b, operator_text="x",
                                                            spoken="Done.") == "widget_data"
    b["result"]["escalate_or_inline"] = {"choice": "escalate", "confidence": 0.95}
    calls = _calls()
    assert probe_after.an_inline_act_settles_the_commission("escalate", calls, brief=b, operator_text="x",
                                                            spoken="Done.") == "escalate"
