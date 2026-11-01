"""Which cards he names to close is decided by ONE reader: the verdict's pick first, the declared names only propose
(V2-831 audit A2b, CRIT-K1).

The class: two readers answered «which cards does he name to close» — the close question over the cards on screen
(`brief_screen.named_to_close`, T-19 R4c) and the declared-names matcher (`named_cards`). `card_close` let the pick win;
`widget_intent`'s close decided «a bulk close or a named one» on the names matcher alone, so a card the verdict picked
but the matcher missed (an alias nobody declared, another language) became «close EVERYTHING».

The door: `canvas_verdict.close_picks(brief)`, read before the names matcher by every close door.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.turn import brief as tb

OPEN = ["agenda", "documento", "mensajeria"]


def _handle(said: str, picks: list[str]) -> dict:
    ev = threading.Event()
    ev.set()
    res = {tb.CANVAS_KEY: ("close", 1.0), tb.NAMES_KEY: ("elsewhere", 0.8)}
    return {"event": ev, "turn_id": "t", "open_ids": list(OPEN), "judged": said, "_close_picks": list(picks),
            "result": {k: {"choice": c, "confidence": p, "probs": {c: p}} for k, (c, p) in res.items()}}


@pytest.fixture
def screen(monkeypatch):
    from nucleo.acts import canvas_turn
    from nucleo.flash import bulk_close
    from server import voice_api
    monkeypatch.setattr(voice_api, "open_instances", lambda: list(OPEN))
    monkeypatch.setattr(bulk_close, "_open_instances", lambda: list(OPEN))
    monkeypatch.setattr(canvas_turn, "request_of", lambda brief=None, text=None, **k: {
        "text": text or "", "turn_credit": True, "last_reply": "", "verdict": {"canvas": ("close", 1.0)}})
    events: list = []

    def emit(kind, action, text=None, role=None, extra=None):
        events.append((kind, action, dict(extra or {})))
    return events, emit


def _closed(events) -> list:
    return [e[2].get("id", "*ALL*") for e in events if e[0] == "widget" and e[1] == "close"]


@pytest.mark.parametrize("said", ["shut the diary for me", "quítame el dietario de delante"])
def test_a_card_the_question_picked_closes_alone_even_when_no_declared_name_matches(screen, said):
    from voice.engine.llm.providers import widget_intent
    events, emit = screen
    assert widget_intent._widget_fallback(said, emit, brief=_handle(said, ["agenda"])) is True
    assert _closed(events) == ["agenda"], "a picked card became a bulk close"


def test_with_no_pick_the_declared_names_still_propose(screen):
    """No close question asked (the names verdict did not stop the close): the matcher's proposal stands, as before."""
    from nucleo.acts import canvas_verdict
    h = _handle("close the calendar", [])
    assert canvas_verdict.close_picks(h) == []


def test_both_close_doors_read_the_same_pick():
    import inspect

    from nucleo.flash import card_close
    from voice.engine.llm.providers import widget_intent
    for mod in (card_close, widget_intent):
        src = inspect.getsource(mod)
        assert "close_picks(" in src and '"_close_picks"' not in src, mod.__name__
