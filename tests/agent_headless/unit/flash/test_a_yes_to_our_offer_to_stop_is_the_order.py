"""A «yes» to OUR offer to stop the errand is the order: it stops, it is not asked again (refactor2710-99).

Use case `docs-single-recipe-not-a-list__us` (2026-10-28): «yeah just give it to me straight» → the model called
`stop_worker`, the verdict was unsure, and the gate asked «Do you want me to stop the task that's running, then?».
He answered «yes, stop it». The model called nothing, the settle backstop read only its grammar (no English, no
«yes»), and nothing stopped; the next turn offered the same stop again.

Now the gate's question is an offer the next turn can take (`stop.offer_taken`). It is read without words: the
brief says his turn ANSWERS (not a question, comment or complaint of his) and the stop verdict points at ending the
errand. Our question is the licence, so the verdict needs only its direction. Both doors honour it: the model's
`stop_worker` runs instead of asking again, and the backstop stops a turn whose model called nothing. A «no» (a
verdict pointing elsewhere) takes nothing, and with no offer of ours an unsure verdict stops nothing.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from nucleo.request import stop as sd
from nucleo.flash import tool_executor_calls as _calls
from nucleo.turn import brief as _tb


@pytest.fixture(autouse=True)
def _no_open_offer():
    sd._OFFER["at"] = 0.0
    yield
    sd._OFFER["at"] = 0.0


def _brief(stop: str | None, confidence: float, *, kind: str = "answer"):
    ev = threading.Event()
    ev.set()
    result = {_tb.REQUEST_KEY: {"choice": kind, "confidence": 0.9}}
    if stop is not None:
        result[sd.KEY] = {"choice": stop, "confidence": confidence}
    return {"event": ev, "turn_id": "t-1", "open_ids": [], "result": result}


def _model_calls_stop(text: str, brief, monkeypatch) -> tuple[list, dict]:
    from nucleo import dispatch
    killed: list = []
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: killed.append(w) or ["1"])
    clarify: dict = {}
    _calls._t_stop_worker(args={"which": "the running errand"}, _norm_nfkd=lambda s: s.lower(),
                          _say=lambda: SimpleNamespace(stop_doubt="Do you want me to stop the task?",
                                                       stop_which_worker="which?"),
                          _says_stop=lambda t: False, clarify=clarify, emit=lambda *a, **k: None, text=text,
                          worker_acted={"v": None}, brief=brief, prior="")
    return killed, clarify


def _backstop(text: str, brief, monkeypatch) -> list:
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: ["1"])
    return sd.repair(brief, text, escalating=False, grammar=lambda: False)


def _we_offer(monkeypatch):
    """Turn 3: the model's stop, an unsure verdict against it → the gate asks (the offer)."""
    killed, clarify = _model_calls_stop("yeah just give it to me straight", _brief("keep", 0.6, kind="order"), monkeypatch)
    assert killed == [] and clarify.get("msg"), "an unsure verdict against the model's stop is asked first"


@pytest.mark.parametrize("yes", ["yes, stop it", "sí, páralo", "yep", "go ahead"])
def test_a_yes_the_model_acts_on_runs_the_stop_instead_of_asking_again(yes, monkeypatch):
    _we_offer(monkeypatch)
    killed, clarify = _model_calls_stop(yes, _brief("keep", 0.6), monkeypatch)
    assert killed == ["the running errand"] and not clarify, "the yes to our offer was turned into another question"


@pytest.mark.parametrize("yes", ["yes, stop it", "sí, páralo", "yep", "go ahead"])
def test_a_yes_the_model_ignores_is_stopped_by_the_backstop(yes, monkeypatch):
    _we_offer(monkeypatch)
    assert _backstop(yes, _brief("stop", 0.4), monkeypatch) == ["1"], "the yes to our offer stopped nothing"


def test_a_no_to_our_offer_takes_nothing(monkeypatch):
    _we_offer(monkeypatch)
    assert _backstop("no, let it finish", _brief("keep", 0.7), monkeypatch) == []


def test_his_own_question_is_not_an_answer_to_ours(monkeypatch):
    _we_offer(monkeypatch)
    assert _backstop("wait, how long will it take?", _brief("stop", 0.4, kind="question"), monkeypatch) == []


def test_without_our_offer_an_unsure_verdict_stops_nothing(monkeypatch):
    assert _backstop("yes, stop it", _brief("stop", 0.4), monkeypatch) == []


def test_the_offer_is_answered_once(monkeypatch):
    _we_offer(monkeypatch)
    assert _backstop("ok", _brief("keep", 0.3), monkeypatch) == []
    assert _backstop("yes, stop it", _brief("stop", 0.4), monkeypatch) == [], "a later turn took a stale offer"
