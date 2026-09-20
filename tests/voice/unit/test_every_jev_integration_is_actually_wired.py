"""Node 3.61 — every Jev integration is WIRED: its real entry point reaches the transport.

WHY THIS FILE EXISTS (V2-726 §7.1). The five Jev tasks each shipped a test file and all five were
green. One of them — `T-jev-router` — never made a single call in its life: `ask_route_async` passed
four positional arguments into `jev.ask_async(text, *, run, name)`, and its own
`except Exception: return None` ate the TypeError. Zero calls in 312 real ones.

Its test file could not fail on that. Every case built the handle BY HAND —
`resolve_route(_handle("show"))` — so it exercised the mapping and never the wiring. The one case
that touched the real entry point asserted `ask_route_async(...) is None` with the kill switch on,
which is exactly what the bug returned. The same `None` meant "switched off" and "broken", and
nothing in the suite could tell them apart.

The rule, and it generalises past Jev: **a test that builds the handle by hand proves the MAPPING,
never the WIRING.** So this file fakes the TRANSPORT (`jev._post_question`, the last thing before
the socket), drives each integration through its own real front door, and asserts the transport was
actually reached. `calls == 1` is the whole point; the verdict is secondary.

The route itself was REMOVED by V2-726 A5 (F0a retired the question: a full stable catalog beats
trimming). What stays is the census below — the set of live integrations is pinned, so the next one
that goes silent, or the next one that appears unannounced, turns this red.
"""
from __future__ import annotations

import pathlib
import time

import pytest

from nucleo import jev


@pytest.fixture
def wire(monkeypatch):
    """Jev ON, the socket replaced. `wire.calls` is what every test here is really asserting."""
    monkeypatch.setattr(jev, "_read_key", lambda: "k-for-tests")
    monkeypatch.delenv("ZAELAR_JEV", raising=False)

    class _Wire:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.choice: str | None = None       # None = answer with the first declared option
            self.confidence = 0.95

        def __call__(self, answer_key, state, instructions, criteria, timeout_s):
            self.calls.append({"key": answer_key, "state": state, "criteria": criteria})
            choice = self.choice if self.choice is not None else next(iter(criteria))
            return {"answers": {answer_key: {"choice": choice, "confidence": self.confidence,
                                             "probabilities": {choice: self.confidence}}}}

    w = _Wire()
    monkeypatch.setattr(jev, "_post_question", w)
    # `_post` is the request-type specialisation the filler test already fakes; route it through
    # the same spy so one counter sees every question.
    monkeypatch.setattr(jev, "_post", lambda state, t: w("request_type", state, "",
                                                          jev.REQUEST_TYPES, t))
    return w


def _settle(handle, timeout_s: float = 2.0):
    """Wait for a fire-and-forget handle. Tests may wait; the PRODUCT never does (that is `peek`)."""
    if handle and handle.get("event"):
        handle["event"].wait(timeout_s)
    return handle


# ── the four that are wired ──────────────────────────────────────────────────────────────────────
def test_the_filler_request_type_reaches_the_transport(wire):
    _settle(jev.request_async("open my messages"))
    assert len(wire.calls) == 1, "the filler never asked Jev anything"
    assert wire.calls[0]["key"] == "request_type"


def test_the_canvas_verb_reaches_the_transport(wire):
    from nucleo.flash import show_target as st
    _settle(st.ask_canvas_async("abre mis mensajes"))
    assert len(wire.calls) == 1, "the canvas verb never asked Jev anything"
    assert wire.calls[0]["key"] == "canvas"
    assert set(wire.calls[0]["criteria"]) == {"show", "close", "neither"}


def test_the_escalate_gate_reaches_the_transport(wire):
    from nucleo.flash import escalation_guard as eg
    eg.judge_escalation("¿qué hora es?")
    assert len(wire.calls) == 1, "the escalate gate never asked Jev anything"
    assert wire.calls[0]["key"] == "escalate_or_inline"


def test_the_action_repair_reaches_the_transport(wire):
    from nucleo.flash import frontend as fe
    fe.repair_action("agenda", "una_accion_inventada", "borra la cita del dentista")
    assert len(wire.calls) == 1, "the action repair never asked Jev anything"
    assert wire.calls[0]["key"] == "widget_action"
    # Rule 2 of the initiative, proved rather than trusted: the options are the DECLARED actions.
    assert "none" in wire.calls[0]["criteria"]


def test_the_live_integrations_are_exactly_these_four(wire):
    """The census. Every integration that talks to Jev is named here, and the list is the assertion.

    It was written when ONE of five was silently dead (the route, V2-726 §3.1) and it stays now that
    the route is gone, because it catches both directions: an integration that STOPS reaching the
    transport, and one that starts reaching it without being declared. Either is a §3.1 in the
    making — the first failure mode took a whole implementation to notice.
    """
    from nucleo.flash import escalation_guard as eg, frontend as fe, show_target as st
    fired = []
    for name, fn in (("filler", lambda: _settle(jev.request_async("open my messages"))),
                     ("canvas", lambda: _settle(st.ask_canvas_async("abre mis mensajes"))),
                     ("action", lambda: fe.repair_action("agenda", "inventada", "borra la cita")),
                     ("escalate", lambda: eg.judge_escalation("¿qué hora es?"))):
        before = len(wire.calls)
        fn()
        if len(wire.calls) > before:
            fired.append(name)
    assert fired == ["filler", "canvas", "action", "escalate"], (
        f"the set of LIVE Jev integrations changed: {fired}. One that went silent is a new "
        f"V2-726 §3.1; one that appeared is an integration nobody declared.")


def test_the_retired_route_is_gone_from_the_engine(wire):
    """A5's own metric: the cancelled integration is REMOVED, not repaired.

    Repairing it would have reinstated a design F0a measured and rejected — and its quiet-chat
    branch could empty the tool set outside `select_for_turn`'s disabled-by-default gate.
    """
    from nucleo.flash import tool_selection as tsel
    for gone in ("ask_route_async", "resolve_route", "ROUTE_KINDS", "ROUTE_INSTRUCTIONS"):
        assert not hasattr(tsel, gone), f"`tool_selection.{gone}` is back — V2-726 F3 was cancelled"
    provider = (pathlib.Path(__file__).resolve().parents[3]
                / "voice" / "engine" / "llm" / "providers" / "nucleo.py").read_text(encoding="utf-8")
    code = "\n".join(l.split("#", 1)[0] for l in provider.splitlines())
    assert "ask_route_async" not in code and "resolve_route" not in code, (
        "the voice provider still fires or consumes the retired route pre-choice")
    assert wire.calls == [], "nothing in this test may reach the transport"


# ── off is off, and it must not look like broken ─────────────────────────────────────────────────
def test_switched_off_reaches_nothing_at_all(wire, monkeypatch):
    """`ZAELAR_JEV=0` is the parity switch. It returns None — and so does a broken integration,
    which is why `assert ... is None` can never be the proof that something is wired."""
    from nucleo.flash import show_target as st
    monkeypatch.setenv("ZAELAR_JEV", "0")
    assert st.ask_canvas_async("abre mis mensajes") is None
    assert jev.request_async("open my messages") is None
    assert wire.calls == [], "something talked to Jev with the kill switch on"
