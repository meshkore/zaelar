"""Jev canvas-verb pre-classifier (T-jev-show-close): the VERB before the model writes text.

The contract under test: Jev names ONLY show / close / neither, and both channels share the
verdict through `show_target.resolve_canvas_verb` — never a second implementation. A ready,
confident verb is returned with `used=True`; anything else — disabled, slow, failed, unsure,
unknown — falls back to "neither", i.e. today's path bit-for-bit. The TARGET is not decided
here (that stays with `resolve_show` / close guards); a "neither" never vetoes them.
"""
from __future__ import annotations

import threading

import pytest

from nucleo import jev
from nucleo.flash import show_target as st


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("ZAELAR_JEV_TIMEOUT_MS", "900")
    monkeypatch.delenv("ZAELAR_JEV", raising=False)
    yield


def _ready_handle(result: dict | None) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": result}


def _canned(choice="show", confidence=0.9):
    return {"model": "jev-latest",
            "answers": {"canvas": {"type": "choice", "choice": choice,
                                   "probabilities": {choice: confidence},
                                   "confidence": confidence}}}


# ── the verb catalog: exactly the three verbs, nothing else ──────────────────────────────
def test_the_canvas_question_offers_show_close_and_neither(monkeypatch):
    monkeypatch.setattr(jev, "_read_key", lambda: "k")
    seen: dict = {}

    def _fake(answer_key, state, instructions, criteria, timeout):
        seen.update(answer_key=answer_key, instructions=instructions,
                    criteria=criteria, state=state)
        return _canned("close")

    monkeypatch.setattr(jev, "_post_question", _fake)
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)
    out = jev.choose_sync("canvas", "ciérralo", instructions=st.CANVAS_INSTRUCTIONS,
                          criteria=st.CANVAS_VERBS, question_id="canvas")
    assert set(seen["criteria"]) == {"show", "close", "neither"}
    assert seen["answer_key"] == "canvas"
    assert "ciérralo" in seen["state"]
    assert out["choice"] == "close"


# ── the shared resolver: confident verb passes, anything else is "neither" ───────────────
def test_a_confident_show_verdict_is_used():
    h = _ready_handle({"choice": "show", "confidence": 0.9, "probs": {"show": 0.9},
                       "latency_ms": 120})
    verb, info = st.resolve_canvas_verb(h)
    assert verb == "show"
    assert info["used"] is True


def test_an_unsure_verdict_falls_back_to_neither():
    """The load-bearing guard: a shrug must not move the canvas. Removing the gate turns this red."""
    h = _ready_handle({"choice": "close", "confidence": 0.2, "probs": {"close": 0.2},
                       "latency_ms": 120})
    verb, info = st.resolve_canvas_verb(h)
    assert verb == "neither"
    assert info["used"] is False


def test_a_verdict_still_flying_falls_back_to_neither():
    h = {"event": threading.Event(), "result": None}
    assert st.resolve_canvas_verb(h) == ("neither", None)
    assert st.resolve_canvas_verb(None) == ("neither", None)


def test_an_unknown_choice_abstains_to_neither(monkeypatch):
    monkeypatch.setattr(jev, "_post_question", lambda *a: _canned(choice="teleport"))
    monkeypatch.setattr(jev, "_read_key", lambda: "k")
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)
    out = jev.choose_sync("canvas", "hello?", instructions=st.CANVAS_INSTRUCTIONS,
                          criteria=st.CANVAS_VERBS, question_id="canvas")
    assert out["choice"] == ""
    verb, info = st.resolve_canvas_verb(_ready_handle(out))
    assert verb == "neither" and info["choice"] == ""


# ── disabled / keyless / failed: today's path, zero behavior change ──────────────────────
def test_no_key_means_no_thread_and_no_verdict(monkeypatch):
    monkeypatch.setattr(jev, "_read_key", lambda: "")
    assert st.ask_canvas_async("abre la agenda") is None
    assert jev.choose_sync("canvas", "abre la agenda", instructions=st.CANVAS_INSTRUCTIONS,
                           criteria=st.CANVAS_VERBS, question_id="canvas") is None


def test_an_explicit_switch_disables_even_with_a_key(monkeypatch):
    monkeypatch.setattr(jev, "_read_key", lambda: "k")
    monkeypatch.setenv("ZAELAR_JEV", "0")
    assert st.ask_canvas_async("abre la agenda") is None


def test_a_failed_call_returns_none_and_logs_the_error(monkeypatch):
    def _boom(*a):
        raise TimeoutError("slow")
    monkeypatch.setattr(jev, "_post_question", _boom)
    monkeypatch.setattr(jev, "_read_key", lambda: "k")
    seen: list = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda kind, label, text="", role="", extra=None: seen.append(extra))
    assert jev.choose_sync("canvas", "hello?", instructions=st.CANVAS_INSTRUCTIONS,
                           criteria=st.CANVAS_VERBS, question_id="canvas") is None
    assert seen and seen[0]["error"].startswith("TimeoutError")


# ── arm/fire: the async handle resolves through the SAME shared resolver ─────────────────
def test_the_async_handle_resolves_through_the_shared_resolver(monkeypatch):
    monkeypatch.setattr(jev, "_post_question", lambda *a: _canned("show"))
    monkeypatch.setattr(jev, "_read_key", lambda: "k")
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)
    h = st.ask_canvas_async("muéstrame la agenda")
    assert h is not None
    assert h["event"].wait(5), "the Jev thread never delivered"
    verb, info = st.resolve_canvas_verb(h)
    assert (verb, info["used"]) == ("show", True)
    assert info["latency_ms"] >= 0


# ── close_has_order: the one reader both [[close]] guards share ──────────────────────────
def _sure_close_handle(confidence=0.9) -> dict:
    return _ready_handle({"choice": "close", "confidence": confidence,
                          "probs": {"close": confidence}, "latency_ms": 120})


def test_grammar_close_needs_no_jev():
    assert st.close_has_order("cierra el widget de música") == (True, "grammar")


def test_a_confident_jev_close_licenses_a_grammar_miss():
    """The behavior this wiring adds: the model said [[close]], the grammar sees no close verb,
    Jev independently reads a close order → let it through. Removing the license turns this red."""
    assert st.close_has_order("please put that away", _sure_close_handle()) == (True, "jev")


def test_an_unsure_jev_keeps_the_discard():
    h = _ready_handle({"choice": "close", "confidence": 0.2, "probs": {}, "latency_ms": 50})
    assert st.close_has_order("please put that away", h) == (False, "none")
    assert st.close_has_order("please put that away", None) == (False, "none")


def test_a_negated_close_vetoes_even_a_confident_jev():
    """The load-bearing veto (V2-678 shape): «do not close» + a Jev false-positive must still
    discard. Removing the veto turns this red."""
    assert st.close_has_order("Do not close the widgets.", _sure_close_handle()) == (False, "none")
