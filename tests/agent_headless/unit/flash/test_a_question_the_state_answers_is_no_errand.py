"""A question the verdict reads as «question · tell · handle_inline» is answered from the turn's state, never
delegated to a worker — whatever it asks and in whatever language (2026-10-21).

Manual session 374a2ae2: «did I send you a long prompt yesterday?» — the brief read all three, the model called
`escalate_to_slowbrain` anyway with «let me get that», and the commission gate kept it because the reply PROMISED.
A worker then spent four minutes failing to find what the turn's own record held. The verdict decides, not the
words: a fourth disposition, ANSWERED, annuls the commission. Since V2-851 F5 (CRIT K34) Flash answers from the state
in the MAIN stream — the model has it in its prompt — and no second pass composes it: a stream that said nothing keeps
the commission (a worker answers rather than silence).
"""
import pytest

from nucleo.flash import escalation_guard as eg
from nucleo.flash import post_stream_acts as psa

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


def _gate(spoken, disposition):
    req = {"v": "recover what the assistant did yesterday", "more": ["x"]}
    kept = (req["v"], list(req["more"]))
    req["v"], req["more"] = None, []                     # what settle_commission did on an annul
    events = []
    psa._keep_unanswered({"disposition": disposition}, kept, req, spoken, lambda *a, **k: events.append(a))
    return req, events


def test_k34_flash_answers_from_the_state_in_its_own_stream():
    """CRIT K34 door test: the commission stays annulled only when the main stream answered — nothing composes it."""
    req, events = _gate(["Yesterday you gave me a list of 26 tasks."], eg.ANSWERED)
    assert req["v"] is None and not events


def test_k34_a_silent_stream_keeps_the_commission():
    req, events = _gate([], eg.ANSWERED)
    assert req["v"] == "recover what the assistant did yesterday" and req["more"] == ["x"] and events
    req, _ = _gate([], eg.PROMISED)
    assert req["v"] is None, "only an ANSWERED annul is given back"


def test_the_turn_wires_it_and_composes_nothing():
    """One turn, typed or spoken (refactor2710-01): it settles, gives a silent ANSWERED back, and runs no model."""
    src = open("nucleo/flash/post_stream_acts.py", encoding="utf8").read()
    assert "_keep_unanswered(_settled, _kept, escalate_req, spoken, emit)" in src
    assert "answered_from_state" not in src and "second_pass" not in src


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
