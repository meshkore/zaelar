"""His answer to a question OUR phase asked never reaches a live errand as a criterion (node 2.706).

search-restaurant-occasion EN (2026-10-14, sandbox 104440-en): the introduction pack rode «ok, let me know» and the
reply asked «where are you based these days?». «San Francisco. ok, let me know when you have options» was read as a
refinement of the Portland errand (`promised_refinement`) and injected whole; the worker searched San Francisco.
"""
from __future__ import annotations

import types

import pytest

from nucleo import dispatch
from nucleo import dispatch_confirm as dc
from nucleo.context_packs import ridden
from nucleo.flash import reply_promise
from nucleo.turn import errands_of_a_turn as E, our_question as Q

ERRAND = {"id": "2", "request": "Find anniversary restaurant options in Portland: quiet, good reviews, about $60 a person",
          "phase": "", "waiting_on": ""}
OURS = ("I'm on it — I'll let you know as soon as I have something. While that runs: where are you based these days? "
        "It'll help me fine-tune things like this for you.")
HIS = "San Francisco. ok, let me know when you have options"
PROMISE = "Got it — San Francisco noted. The Portland search is still running, and I'll let you know the moment I have options."


@pytest.fixture
def portland(monkeypatch):
    sent = []
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(ERRAND)])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label=""))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    monkeypatch.setattr(dispatch, "inject_soon", lambda which, msg: sent.append((which, msg)))
    monkeypatch.setattr(reply_promise, "promises_action", lambda r: r == PROMISE)
    monkeypatch.setattr(Q, "previous_reply", lambda spoken="": OURS)
    ridden.forget()
    yield sent
    ridden.forget()


def test_the_answer_is_cut_when_the_phase_asked(portland):
    ridden.note("ok, let me know", True)
    ridden.note(HIS, True)
    assert E.words_for(HIS, PROMISE) == "ok, let me know when you have options"
    assert "San Francisco" not in E.words_for(HIS, PROMISE)


def test_the_voice_backstop_injects_only_the_rest(portland):
    from voice.engine.llm.providers import promise_backstop as pb
    ridden.note("ok, let me know", True)
    ridden.note(HIS, True)
    pb._a_refinement_of_the_errand_it_names(PROMISE, HIS, lambda *a, **k: None)
    assert all("San Francisco" not in m for _w, m in portland), portland


def test_a_bare_answer_routes_nowhere(portland):
    ridden.note("ok, let me know", True)
    ridden.note("Portland, Oregon", True)
    assert E.promised_refinement("Portland, Oregon", PROMISE) == "", "the whole turn was the answer"


def test_without_the_phase_his_words_are_his_errand_s(portland):
    ridden.note("ok, let me know", False)
    ridden.note(HIS, False)
    assert E.words_for(HIS, PROMISE) == HIS, "a question about the errand gets its answer to the errand"


def test_the_last_question_is_read_past_a_trailing_sentence():
    assert Q.last_question(OURS).startswith("While that runs: where are you based")
    assert Q.last_question("I'll tell you as soon as it lands.") == ""
