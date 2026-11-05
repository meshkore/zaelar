"""A «yes» to a waiting task opens no second task (V2-854 F4, V2-851 §3a, I1).

Measured on his engine (2026-11-05 17:22, «Sí, mándaselo»): the binding verdict tied his words to the waiting send's
question and the waiting task sent ONCE — but the same turn's escalation had already gone through the catalogue rung
into a SECOND `mensajeria:send_to`, which opened a confirmation and asked «Shall I send it?» again. The binding that
clears the turn's escalation ran after the rungs. Now the same verdict is read FIRST: a bound answer's turn opens no
errand and no card act, and a confirmation the turn itself opened for an act that leaves the machine is withdrawn
when the answer binds — a non-leaving confirmation of the same turn stays.
"""
from __future__ import annotations

import inspect

import pytest

from nucleo.cli import worker_api, worker_api_bind as bind
from nucleo.flash import post_stream_acts, post_stream_settle as pss
from nucleo.turn import verdicts
from voice import trace
from widgets import confirm

ASK = {"task_id": "r7-1", "ask_id": "r7-1-q1", "question": "Shall I send it?", "title": "Message to Nerea",
       "since": 1, "candidates": [], "said": True}
TURNS = {
    "es": ("Sí, mándaselo.", "Enviar un WhatsApp a Nerea preguntándole cuándo vuelve"),
    "en": ("Yes, book it.", "Book a table for two at the Thai place on Friday at nine"),
}


@pytest.fixture
def waiting(monkeypatch):
    st = {"choice": ASK["ask_id"], "conf": 0.82, "events": []}
    monkeypatch.setattr(worker_api, "open_asks", lambda: [dict(ASK)])
    monkeypatch.setattr(verdicts, "read", lambda h, key, fb, min_confidence=None:
                        (st["choice"], {"confidence": st["conf"]}) if key == bind.KEY else (fb, None))
    st["emit"] = lambda *a, **k: st["events"].append((a, k))
    yield st
    confirm.reset()
    trace.adopt("")


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_bound_answer_opens_no_errand_of_its_own(waiting, lang):
    words, commission = TURNS[lang]
    esc = {"v": commission, "more": ["and another thing"], "surface": {}}
    assert pss.no_new_errand_for_a_bound_answer(esc, {}, worker_acted={"v": None}, emit=waiting["emit"])
    assert esc["v"] is None and esc["more"] == [], "the answer's turn still carries an errand to the rungs"
    assert waiting["events"], "the dropped commission left no trace"


@pytest.mark.parametrize("choice, conf", [(bind.NONE, 0.9), (ASK["ask_id"], 0.3)])
def test_a_turn_that_answers_no_waiting_task_keeps_its_errand(waiting, choice, conf):
    waiting["choice"], waiting["conf"] = choice, conf
    esc = {"v": TURNS["en"][1], "more": [], "surface": {}}
    assert not pss.no_new_errand_for_a_bound_answer(esc, {}, worker_acted={"v": None}, emit=waiting["emit"])
    assert esc["v"] == TURNS["en"][1]


def test_the_guard_runs_before_any_rung_can_turn_the_errand_into_an_act():
    src = inspect.getsource(post_stream_acts.complete_the_acts)
    guard = src.index("no_new_errand_for_a_bound_answer(")
    for rung in ("_show_guard_target(", "take_rung(", "before_worker("):
        assert guard < src.index(rung), f"{rung} runs before the bound answer is read"


def test_the_turns_own_leaving_confirmation_is_withdrawn_when_the_answer_binds(waiting, monkeypatch):
    trace.adopt("T-yes")
    confirm.request("data", "mensajeria", "Shall I send it?", op={"action": "send_to", "payload": {"contact": "Nerea"}},
                    notify_ui=False)
    confirm.request("data", "agenda", "Clear the whole agenda?", op={"action": "clear_all", "payload": {}},
                    notify_ui=False)
    sent, state = [], {"opened": "Shall I send it?"}
    monkeypatch.setattr(worker_api, "answer_soon", lambda *a: sent.append(a) or True)
    acted, esc = {"v": None}, {"v": None, "more": []}
    pss.bind_the_answer({}, TURNS["es"][0], model_answer="", worker_acted=acted, escalate_req=esc, others_acted=False,
                        spoken_text="", send=lambda *_: None,
                        speech=type("S", (), {"sanitize": staticmethod(lambda t, **_: t)}), emit=waiting["emit"],
                        confirm_state=state)
    assert sent and acted["v"] == "answer"
    assert "mensajeria" not in confirm.pending(), "the act the waiting task owns is asked a second time"
    assert "agenda" in confirm.pending(), "a confirmation for an act that stays on the machine was withdrawn"
    assert state["opened"] == "", "the withdrawn question would still be spoken"


def test_another_turns_confirmation_is_never_withdrawn(waiting, monkeypatch):
    trace.adopt("T-earlier")
    confirm.request("data", "mensajeria", "Shall I send it?", op={"action": "send_to", "payload": {}}, notify_ui=False)
    trace.adopt("T-yes")
    assert pss.withdraw_the_turns_leaving_confirms({"opened": ""}, waiting["emit"]) == []
    assert "mensajeria" in confirm.pending()
