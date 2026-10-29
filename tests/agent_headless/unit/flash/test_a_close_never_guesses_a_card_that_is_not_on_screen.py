"""A close never guesses a card that is not on screen, and where the names verdict ran it decides (demo sandbox
2026-10-29, C6, V2-831 T-19 R4b).

«cierra la agenda y los mensajes» with the agenda open and the messages not: `names_a_card=elsewhere` vetoed the
model's own closes, and then the voice provider's word fallback (`widget_intent._widget_fallback`) picked a card from
the words. `identify` picked one match (the messages, which were NOT open), so the close went to a card that was not
there. Three readers, one class:

  · the fallback closes only cards ON SCREEN that his words name (`instances.also_named`), every one of them, and
    nothing at all when the names verdict says what he named is not on screen;
  · `named_cards` returns every card his words call by its catalogue name, not only the one `identify` matched;
  · the promise door's owed close (`post_stream_acts`, `close_is_owed`) closes every open card the sentence names,
    not only the verdict's card.

Disarm: target `_identify_named` again in the fallback, drop the catalogue-name union from `named_cards`, or close
only the verdict's card in the owed close. Each one turns its tests red.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.turn import brief as tb

MIXED = {"en": "close the calendar and the messages", "es": "cierra la agenda y los mensajes"}


def _brief(open_ids, names) -> dict:
    ev = threading.Event()
    ev.set()
    res = {tb.CANVAS_KEY: ("close", 1.0), tb.NAMES_KEY: names, tb.REQUEST_KEY: ("order", 0.9)}
    return {"event": ev, "turn_id": "t", "open_ids": list(open_ids),
            "result": {k: {"choice": c, "confidence": p, "probs": {c: p}} for k, (c, p) in res.items()}}


@pytest.mark.parametrize("lang", ["en", "es"])
def test_named_cards_reads_both_cards_of_the_sentence(lang):
    from nucleo.flash import direct_action
    assert set(direct_action.named_cards(MIXED[lang])) == {"agenda", "mensajeria"}


@pytest.fixture
def fallback(monkeypatch):
    import server.voice_api as va
    from memory import api as memapi
    from nucleo.acts import canvas
    from voice.engine.llm.providers import widget_intent as wi
    closed, screen = [], {"open": []}
    monkeypatch.setattr(va, "open_instances", lambda: list(screen["open"]))
    monkeypatch.setattr(memapi, "state", lambda: {"open_widgets": list(screen["open"]), "recent_widgets": []})
    monkeypatch.setattr(canvas, "apply", lambda op, wid="", **k: closed.append((op, wid)) or True)

    def run(text, open_ids, names):
        screen["open"] = list(open_ids)
        closed.clear()
        wi._widget_fallback(text, lambda *a, **k: None, ask=lambda m: None, brief=_brief(open_ids, names))
        return [w for op, w in closed if op == "close"]
    return run


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_fallback_closes_the_named_card_on_screen_and_never_the_one_that_is_not(fallback, lang):
    assert fallback(MIXED[lang], ["agenda", "results"], ("on_screen", 0.95)) == ["agenda"]


@pytest.mark.parametrize("lang", ["en", "es"])
def test_both_named_cards_on_screen_both_close(fallback, lang):
    assert sorted(fallback(MIXED[lang], ["agenda", "mensajeria"], ("on_screen", 0.95))) == ["agenda", "mensajeria"]


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_names_verdict_decides_over_the_words(fallback, lang):
    assert fallback(MIXED[lang], ["agenda", "results"], ("elsewhere", 0.98)) == []


@pytest.mark.parametrize("said", ["close the map and the messages", "cierra el mapa y los mensajes"])
def test_another_card_the_same(fallback, said):
    assert fallback(said, ["map", "results"], ("on_screen", 0.95)) == ["map"]


@pytest.mark.parametrize("said", ["close the messages", "cierra los mensajes"])
def test_a_named_card_that_is_not_on_screen_closes_nothing(fallback, said):
    assert fallback(said, ["agenda", "results"], ("on_screen", 0.6)) == []


# ── the real headless turn ────────────────────────────────────────────────────────────────────────────────────
def _turn(lang, names, open_ids, tools=()):
    from tests.brain import harness
    case = {"id": f"r4b-{lang}", "lang": lang, "phrase": MIXED[lang], "source": "demo sandbox 2026-10-29 C6",
            "screen": {"open": list(open_ids)}, "model": {"say": "Both closed.", "tools": list(tools)},
            "brief": {"canvas": ["close", 1.0], "screen_action": ["agenda:close_meeting", 0.5],
                      "names_a_card": list(names), "request_type": ["order", 0.9]},
            "expect": "close agenda", "forbid": ["data-op"]}
    return harness.run_case(case)


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_owed_close_closes_every_named_card_on_screen(lang):
    """An unsure «elsewhere» (0.6) stops the gesture but not the owed close: both open cards close."""
    out = _turn(lang, ("elsewhere", 0.6), ["agenda", "mensajeria"])
    assert out.decision == "close agenda" and "close mensajeria" in out.also, (out.decision, out.also)


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_sandbox_turn_closes_no_card_that_is_not_on_screen(lang):
    out = _turn(lang, ("elsewhere", 0.98), ["agenda", "results"], [{"name": "close_widget",
                                                                     "args": {"widget_id": "agenda"}}])
    assert "close mensajeria" not in out.all_decisions and not [d for d in out.all_decisions
                                                                if d.startswith("data-op")], out.all_decisions
