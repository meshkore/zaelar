"""A question the verdict reads as «question · tell · handle_inline» is answered from the turn's state, never
delegated to a worker — whatever it asks and in whatever language (2026-10-21).

Manual session 374a2ae2: «did I send you a long prompt yesterday?» — the brief read all three, the model called
`escalate_to_slowbrain` anyway with «let me get that», and the commission gate kept it because the reply PROMISED.
A worker then spent four minutes failing to find what the turn's own record held. The verdict decides, not the
words: a fourth disposition, ANSWERED, annuls the commission and a second pass composes the answer from the state.
"""
import asyncio

import pytest

from nucleo.flash import escalation_guard as eg
from nucleo.flash import second_pass as sp

SURE = {"request_type": "question", "wants_words": "tell", "escalate_or_inline": "handle_inline"}


@pytest.fixture
def brief(monkeypatch):
    verdicts = dict(SURE)
    from nucleo.turn import brief as tb
    monkeypatch.setattr(tb, "read", lambda handle, key, fallback, **k: (verdicts.get(key, fallback), None))
    return verdicts


def _settle(reply="Let me get that — I'm running it now.", acted=False):
    req = {"v": "recover what the assistant did yesterday", "more": []}
    v = eg.settle_commission(req, brief=object(), operator_text="what did you do yesterday?", reply=reply,
                             acted=acted, anything_running=False, emit=lambda *a, **k: None)
    return v, req


def test_a_question_the_state_answers_annuls_even_a_promised_commission(brief):
    v, req = _settle()
    assert v["disposition"] == eg.ANSWERED and req["v"] is None, "the worker is not spent on a question"


@pytest.mark.parametrize("key,other", [("request_type", "order"), ("wants_words", "act"),
                                       ("escalate_or_inline", "escalate")])
def test_any_verdict_short_of_all_three_keeps_todays_path(brief, key, other):
    brief[key] = other
    v, req = _settle()
    assert v["disposition"] != eg.ANSWERED and req["v"] is not None, f"{key}={other} is not a question to answer"


def test_a_turn_that_acted_is_not_turned_into_an_answer(brief):
    v, _ = _settle(acted=True)
    assert v["disposition"] != eg.ANSWERED


def test_the_answer_pass_runs_only_for_that_disposition(monkeypatch):
    calls = []

    async def _collect(sys2, user_text, spec, max_tokens=240):
        calls.append(sys2)
        return "Yesterday, Tuesday 20 October, you gave me a list of 26 tasks and all of them were done."

    monkeypatch.setattr(sp, "collect", _collect)
    assert asyncio.run(sp.answered_from_state({"disposition": eg.PROMISED}, "q", [], None)) == ""
    out = asyncio.run(sp.answered_from_state({"disposition": eg.ANSWERED}, "what did you do yesterday?", [], None))
    assert "26 tasks" in out and calls and "ESTADO" in calls[0], "the pass is given the turn's state to answer from"


def test_the_turn_wires_it():
    """One turn, typed or spoken (refactor2710-01): it settles and never composes the answer."""
    voice = open("nucleo/flash/post_stream_acts.py", encoding="utf8").read()
    assert "answered_from_state(_settled" in voice, "the turn settles and never composes the answer"


@pytest.mark.parametrize("surface", ["informe", "lista", "item", "imagenes", "widget"])
def test_a_question_whose_answer_is_something_to_look_at_is_not_answered_from_the_state(brief, surface):
    """«Give me the carbonara recipe» (2026-10-27): question · tell · handle_inline with `errand_surface = informe`.
    Annulled as ANSWERED it was composed from the state alone — «I don't have a carbonara recipe stored here» — and a
    web search ran for minutes. Something to LOOK at goes on to the rung that writes it."""
    brief["errand_surface"] = surface
    v, req = _settle()
    assert v["disposition"] != eg.ANSWERED and req["v"] is not None, surface


@pytest.mark.parametrize("surface", ["voz", "silenciosa", ""])
def test_a_question_whose_answer_is_said_is_still_answered_from_the_state(brief, surface):
    brief["errand_surface"] = surface
    v, _ = _settle()
    assert v["disposition"] == eg.ANSWERED, surface
