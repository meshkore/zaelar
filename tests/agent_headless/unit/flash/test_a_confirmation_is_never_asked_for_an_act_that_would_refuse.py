"""A confirmation is never asked for an act that would refuse the call (V2-852, his engine 2026-11-05).

«mandale un mensaje a raquel…» became `mensajeria:reply` with no `n`; the gate asked «Shall I send it?», he pressed
Yes, and only then the act refused for its empty selector («I couldn't tell which one to remove») — the send never
happened. Then «I don't see the message sent» became `send_draft` and the gate asked about «the draft in the box»
with the box empty. The gate now reads the act first (`widgets.contract.would_refuse`): nothing is registered and the
act's own reason is said. And an act that LEAVES never reaches the gate from Flash at all: it is a task the turn
routes (`tool_executor_widget_calls._leaving_is_a_task`, V2-852 M2) — the worker sends, Flash never does.
"""
from __future__ import annotations

from voice.engine.llm.providers import confirm_gate
from widgets import contract
from widgets.mensajeria import data as mens


def test_a_reply_that_names_no_conversation_is_refused_before_the_question():
    d = confirm_gate.decide("mensajeria", "reply", {"text": "Hola Raquel, te esperamos en casa."})
    assert d["kind"] == "refused" and d["refusal"]["error"] in ("selector_missing", "no_target")
    assert "question" not in d and "op" not in d          # nothing to register: a yes has nothing to run


def test_a_send_of_a_draft_that_is_not_there_is_refused_before_the_question():
    d = confirm_gate.decide("mensajeria", "send_draft", {"messageId": "I don't see the message sent"})
    assert d["kind"] == "refused" and d["refusal"]["error"] == "no_draft"


def test_an_act_that_can_run_is_still_asked(monkeypatch):
    monkeypatch.setattr(mens, "would_refuse", lambda *_a: None)
    d = confirm_gate.decide("mensajeria", "reply", {"n": 1, "text": "hola"})
    assert d["kind"] == "ask" and d["op"]["action"] == "reply"


def test_disarmed_the_gate_asks_about_an_act_that_cannot_run(monkeypatch):
    monkeypatch.setattr(contract, "would_refuse", lambda *_a: None)
    d = confirm_gate.decide("mensajeria", "reply", {"text": "Hola Raquel"})
    assert d["kind"] == "ask"                              # the measured bug, reproduced with the check removed


def test_a_refused_act_says_its_own_reason_not_a_removal():
    d = confirm_gate.decide("mensajeria", "reply", {"text": "Hola Raquel"})
    assert d["sentence"] and "remove" not in d["sentence"].lower() and "quitar" not in d["sentence"].lower()


def test_an_act_that_leaves_is_routed_as_a_task_and_never_run_inline(monkeypatch):
    from nucleo.flash import tool_executor_widget_calls as calls
    from nucleo.request import send_task, send_task_answer
    # a card whose act declares its slots: the call is the SEND TASK on the request's row (2026-11-06), never inline
    monkeypatch.setattr(send_task_answer, "take_call", lambda *a, **k: "")
    monkeypatch.setattr(send_task, "commission", lambda *a, **k: "r-1")
    seen, esc = [], {"v": None}
    assert calls._leaving_is_a_task("mensajeria", "send_to", "mandale un whatsapp a raquel", esc,
                                    lambda *a, **k: seen.append(a[1])) is True
    assert esc.get("send_task") and esc["v"] is None and seen
    # no declared slots: the turn's one escalation carries his words, as before
    monkeypatch.setattr(send_task, "commission", lambda *a, **k: "")
    esc = {"v": None}
    assert calls._leaving_is_a_task("mensajeria", "send_to", "mandale un whatsapp a raquel", esc,
                                    lambda *a, **k: seen.append(a[1])) is True
    assert esc["v"] == "mandale un whatsapp a raquel"


def test_an_act_that_stays_runs_inline():
    from nucleo.flash import tool_executor_widget_calls as calls
    esc = {"v": None}
    assert calls._leaving_is_a_task("agenda", "add_task", "apunta comprar pan", esc, lambda *a, **k: None) is False
    assert esc["v"] is None


def test_disarmed_a_leaving_act_would_run_inline(monkeypatch):
    from nucleo.flash import tool_executor_widget_calls as calls
    from widgets import effects
    monkeypatch.setattr(effects, "leaves", lambda *_a: False)
    esc = {"v": None}
    assert calls._leaving_is_a_task("mensajeria", "send_to", "mandale", esc, lambda *a, **k: None) is False
