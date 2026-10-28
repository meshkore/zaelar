"""A correction of the running errand is one act (V2-820): «not X, Y» stops X AND starts Y; «look there, not here»
reaches X.

Measured on a live session: he asked for an app that would read his sent messages and distil his writing
style; then «no tiene que ser una aplicación… lee cincuenta mensajes y créame ese documento». The model called
`stop_worker` and said «paro lo del widget y me pongo a leer cincuenta de tus mensajes» — the app build stopped and
nothing started. Three minutes later: «te he pedido una cosa y creo que me estás ignorando». The stop question had
two answers, «stop» and «keep», and a stop door never lets the turn's escalation through.

Later, with the document errand running: «no quiero que mires WhatsApp, quiero que mires el email». The reply
promised «le digo al proceso que se limite a tu correo»; nothing told the process — the promise pass opened his
mail card instead — and the worker kept reading WhatsApp.

The turn's brief now answers four ways while an errand runs: stop · replace · steer · keep. A sure `replace` stops
the errand AND the turn carries its replacement, with the stopped errand's goal beside his words; a sure `steer`
relays his words to the ONE running errand before any repair pass can turn the promise into a card op.
"""
from __future__ import annotations

import inspect
import threading
from types import SimpleNamespace

import pytest

from nucleo.request import stop as sd

#: «not X, do Y» in several languages — the stopped errand is the app build, the new one the document.
REPLACE_BANK = [
    ("No hay que crear una app, hay que crear un documento con mi estilo",
     "Crear una app que lea mis mensajes enviados de más de 50 caracteres"),
    ("Forget the app — just read fifty of my sent emails and write me a document about how I write",
     "Build an app that reads my sent messages longer than 50 characters"),
    ("Pas d'application : écris-moi un document sur mon style",
     "Créer une application qui lit mes messages envoyés"),
]

#: «look there, not here» — the errand goes on with his correction.
STEER_BANK = [
    "No quiero que mires WhatsApp. Quiero que mires el email.",
    "Don't look at WhatsApp, look at my email instead.",
    "WhatsAppじゃなくてメールを見て",
]


def _brief(choice: str | None, confidence: float = 0.95):
    ev = threading.Event()
    ev.set()
    result = {} if choice is None else {sd.KEY: {"choice": choice, "confidence": confidence}}
    return {"event": ev, "turn_id": "t-1", "open_ids": [], "result": result}


@pytest.fixture
def one_errand(monkeypatch):
    """One live errand, id «7», goal «the app build»; records what was cancelled and injected."""
    from nucleo import dispatch
    seen = {"cancelled": [], "injected": []}
    rec = SimpleNamespace(goal="Crear una app que lea mis mensajes enviados", waiting_on="")
    monkeypatch.setattr(dispatch, "resolve_sessions", lambda q: ["7"])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: rec if str(tid) == "7" else None)
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: seen["cancelled"].append(w) or ["7"])
    monkeypatch.setattr(dispatch, "inject_soon", lambda w, m: seen["injected"].append((w, m)))
    seen["rec"] = rec
    return seen


# ── replace: one act ─────────────────────────────────────────────────────────────────────────────────────────
def _stopped(goal):
    return {"v": "stop", "stopped": [goal]}


@pytest.mark.parametrize("text,old_goal", REPLACE_BANK)
def test_a_replace_ends_the_errand_like_a_stop(text, old_goal, one_errand):
    assert sd.ordered(_brief("replace"), grammar=False), "the tool gate lets the model's stop run"
    acted: dict = {}
    assert sd.repair(_brief("replace"), text, escalating=True, grammar=lambda: False, acted=acted) == ["7"], \
        "a turn that also escalated still stops the errand it replaces"
    assert acted["stopped"] == ["Crear una app que lea mis mensajes enviados"], "the goal is read before the cancel"


@pytest.mark.parametrize("text,old_goal", REPLACE_BANK)
def test_a_replace_starts_the_errand_he_named_with_the_old_goal_carried(text, old_goal):
    req = {"v": None, "more": []}
    said: list = []
    assert sd.start_beside_the_stop(_brief("replace"), req, text, _stopped(old_goal), emit=lambda *a, **k: said.append(a))
    assert said, "the replacement is said on the timeline"
    assert req["v"].startswith(text), "his words of this turn are the request"
    assert old_goal in req["v"], "what he had asked in the stopped errand is carried, not lost with the cancel"
    assert req["replaces"] == [old_goal]


def test_the_models_own_escalation_keeps_its_words_and_gains_the_carried_goal():
    req = {"v": "Leer 50 correos enviados y redactar un documento con su estilo", "more": []}
    assert sd.start_beside_the_stop(_brief("replace"), req, "no, un documento", _stopped("la app"))
    assert req["v"].startswith("Leer 50 correos enviados") and "la app" in req["v"]


def test_no_stop_this_turn_means_nothing_to_replace():
    req = {"v": None, "more": []}
    assert not sd.start_beside_the_stop(_brief("replace"), req, "un documento", {"v": None})
    assert not sd.start_beside_the_stop(_brief("replace"), req, "un documento", {"v": "inject"})
    assert req["v"] is None


@pytest.mark.parametrize("choice", ["stop", "keep", "steer", None])
def test_only_a_sure_replace_starts_anything(choice):
    req = {"v": None, "more": []}
    assert not sd.start_beside_the_stop(_brief(choice), req, "no, un documento", _stopped("la app"))
    assert req["v"] is None and "replaces" not in req
    assert not sd.start_beside_the_stop(_brief("replace", confidence=0.2), req, "x", _stopped("y")), "unsure → today"


def test_the_goal_is_read_before_the_cancel_purges_it(one_errand):
    assert sd.goals_of("todo") == ["Crear una app que lea mis mensajes enviados"]


def test_the_doors_carry_the_replace():
    """Wiring: the voice tool gate and backstop record what they stopped, the settle step composes the replacement,
    and `turn_after` lets it through beside the stop (and never as a refinement of the dying errand)."""
    from nucleo.flash import post_stream_settle, tool_executor_calls
    from voice.engine.llm.providers import turn_after
    assert 'worker_acted["stopped"] = _stop_decision.goals_of(_w)' in inspect.getsource(
        tool_executor_calls._t_stop_worker)
    assert "acted=worker_acted" in inspect.getsource(post_stream_settle.settle_what_is_pending)
    after = inspect.getsource(turn_after.close_the_turn)
    assert "_replacing = _stop_decision.start_beside_the_stop(_brief, escalate_req, _op_text, worker_acted" in after
    assert '(not worker_acted["v"] or _replacing)' in after
    assert "if not _replacing and _p._similar_pending(req, _prev_pending)" in after


# ── steer: his correction reaches the errand ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", STEER_BANK)
def test_a_steer_reaches_the_one_running_errand(text, one_errand):
    acted, esc = {"v": None}, {"v": "leer mis correos", "more": ["x"]}
    assert sd.steer(_brief("steer"), text, worker_acted=acted, escalate_req=esc) == "7"
    assert one_errand["injected"] == [("7", " ".join(text.split()))]
    assert acted["v"] == "inject", "the turn now counts as acted: no repair pass turns the promise into a card op"
    assert esc == {"v": None, "more": []}, "the model's escalation of his correction is the relay's, not a new errand"


@pytest.mark.parametrize("choice", ["keep", "stop", "replace", None])
def test_only_a_sure_steer_relays(choice, one_errand):
    acted = {"v": None}
    assert sd.steer(_brief(choice), STEER_BANK[0], worker_acted=acted) == ""
    assert one_errand["injected"] == [] and acted["v"] is None


def test_a_steer_never_doubles_what_the_model_already_did(one_errand):
    for already in ("inject", "answer", "stop"):
        assert sd.steer(_brief("steer"), STEER_BANK[1], worker_acted={"v": already}) == ""
    assert one_errand["injected"] == []


def test_a_steer_with_several_errands_or_one_waiting_on_him_is_left_to_today(one_errand, monkeypatch):
    from nucleo import dispatch
    one_errand["rec"].waiting_on = "¿Cuántos mensajes?"
    assert sd.steer(_brief("steer"), STEER_BANK[0], worker_acted={"v": None}) == "", "its answer is another door"
    one_errand["rec"].waiting_on = ""
    monkeypatch.setattr(dispatch, "resolve_sessions", lambda q: ["7", "8"])
    assert sd.steer(_brief("steer"), STEER_BANK[0], worker_acted={"v": None}) == "", "never a guess between two"
    assert one_errand["injected"] == []


def test_the_steer_runs_before_the_promise_pass():
    from nucleo.flash import post_stream_words
    words = inspect.getsource(post_stream_words.hold_the_model_to_its_words)
    assert "_stop_decision.steer(_brief" in words
    assert words.index("_stop_decision.steer(_brief") < words.index("call_for_promise_or_order"), \
        "a relay that ran after the repair pass would come too late: the card op already ran"


def test_the_question_offers_the_four_answers():
    assert set(sd.question("")["criteria"]) == {"stop", "replace", "steer", "keep"}
    assert [c for c in sd.CHOICES if sd.ends(c)] == ["stop", "replace"]
