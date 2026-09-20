"""Jev request-type classifier for the filler (first caller of nucleo/jev.py).

The contract under test: Jev is advisory. A ready, confident verdict moves the cover to the
matching pool; anything else — disabled, slow, failed, unsure — keeps the regex class, and every
completed call leaves one observability event with verdict + milliseconds.
"""
from __future__ import annotations

import threading

import pytest

from nucleo import jev
from voice.engine.speech import filler_audio as fa


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    fa._reset_for_tests()
    monkeypatch.setenv("ZAELAR_JEV_TIMEOUT_MS", "900")
    monkeypatch.delenv("ZAELAR_JEV", raising=False)
    yield
    fa._reset_for_tests()


def _ready_handle(result: dict | None) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": result}


# ── the type catalog maps onto real filler pools ──────────────────────────────────────────────
def test_every_request_type_maps_to_a_pool_that_pick_filler_knows():
    from i18n import langs
    for rtype, kind in jev.KIND_MAP.items():
        assert rtype in jev.REQUEST_TYPES, f"{rtype} has a pool but no question option"
        pool = {"neutral": "fillers", "action": "fillers_action",
                "social": "fillers_social", "ack": "fillers_ack"}[kind]
        assert getattr(langs.spec("es"), pool), f"{rtype} -> {kind} ships no pool"
        assert getattr(langs.spec("en"), pool), f"{rtype} -> {kind} ships no pool"


def test_an_order_gets_motion_and_an_answer_gets_a_receipt():
    assert jev.KIND_MAP["order"] == "action"
    assert jev.KIND_MAP["answer"] == "ack"
    assert jev.KIND_MAP["question"] == "neutral"


# ── the confidence gate ──────────────────────────────────────────────────────────────────────
def test_a_confident_verdict_moves_the_cover():
    h = _ready_handle({"type": "order", "kind": "action", "confidence": 0.9,
                       "probs": {"order": 0.9}, "latency_ms": 120})
    kind, info = jev.resolve_kind(h, "neutral")
    assert kind == "action"
    assert info["used"] is True


def test_an_unsure_verdict_keeps_the_regex_class():
    """The load-bearing guard: a shrug must not move the cover. Removing the gate turns this red."""
    h = _ready_handle({"type": "order", "kind": "action", "confidence": 0.2,
                       "probs": {"order": 0.2}, "latency_ms": 120})
    kind, info = jev.resolve_kind(h, "neutral")
    assert kind == "neutral"
    assert info["used"] is False


def test_a_verdict_still_flying_keeps_the_regex_class():
    h = {"event": threading.Event(), "result": None}
    assert jev.resolve_kind(h, "social") == ("social", None)
    assert jev.resolve_kind(None, "social") == ("social", None)


# ── disabled / keyless: pure regex path, zero behavior change ───────────────────────────────
def test_no_key_means_no_thread_and_no_verdict(monkeypatch):
    monkeypatch.setattr(jev, "_read_key", lambda: "")
    assert jev.enabled() is False
    assert jev.request_async("open the music") is None
    assert jev.classify_sync("open the music") is None


def test_an_explicit_switch_disables_even_with_a_key(monkeypatch):
    monkeypatch.setattr(jev, "_read_key", lambda: "k")
    monkeypatch.setenv("ZAELAR_JEV", "0")
    assert jev.enabled() is False


# ── the wire + the observability event ───────────────────────────────────────────────────────
def _canned(choice="order", confidence=0.87):
    return {"model": "jev-latest",
            "answers": {"request_type": {"type": "choice", "choice": choice,
                                         "probabilities": {choice: confidence},
                                         "confidence": confidence}}}


def test_a_call_parses_and_logs_verdict_with_milliseconds(monkeypatch):
    monkeypatch.setattr(jev, "_post", lambda state, timeout: _canned())
    monkeypatch.setattr(jev, "_read_key", lambda: "k")
    seen: list = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda kind, label, text="", role="", extra=None: seen.append(
                            (kind, label, text, extra)))
    out = jev.classify_sync("close the widgets")
    assert out["type"] == "order" and out["kind"] == "action"
    assert out["latency_ms"] >= 0
    assert len(seen) == 1
    kind, label, text, extra = seen[0]
    assert label == "jev request-type"
    assert extra["latency_ms"] >= 0 and extra["choice"] == "order"
    assert extra["probabilities"] == {"order": 0.87}
    assert "close the widgets" in text


def test_a_failed_call_returns_none_and_logs_the_error(monkeypatch):
    def _boom(state, timeout):
        raise TimeoutError("slow")
    monkeypatch.setattr(jev, "_post", _boom)
    monkeypatch.setattr(jev, "_read_key", lambda: "k")
    seen: list = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda kind, label, text="", role="", extra=None: seen.append(extra))
    assert jev.classify_sync("hello?") is None
    assert seen and seen[0]["error"].startswith("TimeoutError")


def test_an_unknown_choice_is_not_a_verdict(monkeypatch):
    monkeypatch.setattr(jev, "_post", lambda state, timeout: _canned(choice="teleport"))
    monkeypatch.setattr(jev, "_read_key", lambda: "k")
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)
    out = jev.classify_sync("hello?")
    assert out["type"] == "" and out["kind"] == ""
    kind, _ = jev.resolve_kind(_ready_handle(out), "neutral")
    assert kind == "neutral"


# ── arm/fire integration: Jev re-classes at the deadline, never blocks it ───────────────────
class _Brain:
    _last_reply = ""
    _last_filler = ""


def _ready_brief(choice, confidence=0.9):
    """A turn brief that has already landed, carrying one request-type verdict.

    Shape-compatible with what `jev.ask_many` returns, because that is what `arm` is handed now:
    since V2-726 A2 the filler does not ask anything — the turn's brief carries its question.
    """
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {"request_type": {"choice": choice, "confidence": confidence,
                                                     "probs": {}}, "_latency_ms": 80}}


def test_a_confident_verdict_in_the_BRIEF_reclasses_the_armed_turn():
    fa.arm(_Brain(), "is it done?", brief=_ready_brief("order"))
    assert fa._jev_brief is not None
    _, kind, _ = fa._consume_arm()
    new_kind, info = fa._consume_jev_kind(kind)
    assert (new_kind, info["used"]) == ("action", True)
    assert fa._consume_jev_kind("neutral") == ("neutral", None), "one turn, one verdict"


def test_the_filler_opens_NO_socket_of_its_own(monkeypatch):
    """V2-726 A2, and the reason this question moved: `arm` used to call `jev.request_async` about a
    second after the brief was fired — same turn, same words, a second round trip for a verdict read
    at the same deadline. Two trips per turn was the measured cost; this is the test that keeps it
    at one. A `request_async` that fires here again turns this red."""
    fired: list = []
    monkeypatch.setattr("nucleo.jev.request_async",
                        lambda *a, **k: fired.append(a) or None)
    fa.arm(_Brain(), "is it done?", brief=_ready_brief("order"))
    assert fired == [], "the filler asked Jev on its own instead of reading the turn's brief"
    _, kind, _ = fa._consume_arm()
    assert fa._consume_jev_kind(kind)[0] == "action", "…and it still got its verdict"


def test_an_unsure_verdict_in_the_brief_keeps_the_regex_class():
    """The gate is where it always was: below MIN_CONFIDENCE the cover keeps the class the model was
    promised. A wrong-class cover is the worse failure (the operator's «Good question» for an order)."""
    fa.arm(_Brain(), "is it done?", brief=_ready_brief("order", confidence=0.3))
    _, kind, _ = fa._consume_arm()
    assert fa._consume_jev_kind(kind)[0] == kind


def test_without_a_brief_the_fire_path_is_byte_identical():
    """Jev off, no key, an open breaker, a brief that failed to build: all of them arrive here as
    `brief=None`, and all of them must be today's path."""
    fa.arm(_Brain(), "is it done?", brief=None)
    _, kind, phrase = fa._consume_arm()
    assert fa._consume_jev_kind(kind) == (kind, None)
    assert phrase != ""
