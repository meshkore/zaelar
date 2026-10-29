"""A known close phrase for a card that is NOT on screen is not «All set.» (V2-831 T-19 R4d).

The action map closes by phrase with no model: «close the map» → `close_widget` → «All set.». When the canvas has
reported what is open and the card is not among it, that close is a no-op and the acknowledgement a false claim.
Such a turn now falls through to the model, which sees the canvas and says the card is not open. An EMPTY report
still means «don't know» (`open_instances` after a restart) and keeps the fast lane as it was.

Disarm: drop the `_open and not options` condition in `executor.execute` → red.
"""
from __future__ import annotations

from nucleo.actionmap import executor


def _close(monkeypatch, open_cards, widget="mapa"):
    from server import voice_api
    monkeypatch.setattr(voice_api, "open_instances", lambda: open_cards)
    monkeypatch.setattr(executor, "_resolve_widget", lambda w: w)
    seen = []
    ok = executor.execute({"do": "close_widget", "widget": widget},
                          lambda kind, label, **k: seen.append((label, (k.get("extra") or {}).get("id"))),
                          phrase="close the map")
    return ok, seen


def test_a_card_the_canvas_says_is_not_open_falls_through_to_the_model(monkeypatch):
    ok, seen = _close(monkeypatch, ["agenda", "youtube"])
    assert ok is False and not seen, f"a close of a card not on screen was acted and acknowledged: {seen}"


def test_a_card_on_screen_still_closes_in_the_fast_lane(monkeypatch):
    ok, seen = _close(monkeypatch, ["agenda", "mapa"])
    assert ok and ("close", "mapa") in seen, seen


def test_an_unknown_canvas_keeps_the_fast_lane(monkeypatch):
    ok, seen = _close(monkeypatch, [])
    assert ok and ("close", "mapa") in seen, seen
