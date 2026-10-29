"""A reply that promises a card act the turn did not run is kept by the second pass, never by a promise table
(demo sandbox 2026-10-29, U2; V2-831 T-19 R7).

«no, put like a prayer» with Madonna on the music card → «Switching to Like a Prayer.» and no call. The English
playback-promise grammar that once kept it (`playback_promise`) went with the promise tables (refactor2710-03), and the
turn's own repair is the door now: the promise repair asks its second pass on the card a verdict names (here the late
catalogue question, because the screen verdict was unsure), through the same canvas reader as every second pass
(`act_repair.canvas_holds_the_turn`). With no verdict naming a card the pass gets nothing and the honest line is said
instead (another writer's).

In the sandbox the turn never reached the door: the steer verdict relayed the sentence to the running errand and the
turn counted as acted. That gate belongs to `nucleo/request/stop.py`. These turns run with no errand, so no relay.

Disarm: make the promise repair's door return None (`call_for_promise_or_order`), or make the reader refuse every inner
op. The play turns go red.
"""
from __future__ import annotations

import pytest

PHRASE = {"en": ("no, put like a prayer", "Switching to Like a Prayer."),
          "es": ("no, pon like a prayer", "Cambio a Like a Prayer.")}


@pytest.fixture
def second_pass_plays(monkeypatch):
    from tests.brain import harness

    async def complete(self, messages, spec=None, *a, **kw):
        harness.RecordedModel.consulted = True
        if kw.get("on_tool_call") and kw.get("tools"):
            kw["on_tool_call"]("widget_data", {"widget_id": "musica", "action": "play",
                                               "payload": {"query": "Like a Prayer"}})
        return ""
    monkeypatch.setattr(harness.RecordedModel, "complete", complete)


def _turn(lang: str, *, late_card: str, monkeypatch):
    from nucleo.flash import card_commission
    from tests.brain import harness
    monkeypatch.setattr(card_commission, "late_catalogue", lambda text, wait_s=3.5: (late_card, 0.9 if late_card else 0.0))
    phrase, said = PHRASE[lang]
    case = {"id": f"u2-{lang}", "lang": lang, "phrase": phrase, "source": "demo sandbox 2026-10-29 U2",
            "screen": {"open": ["results", "agenda", "musica"]},
            "history": [{"role": "user", "text": "play some madonna"}, {"role": "assistant", "text": "Madonna coming up."}],
            "model": {"say": said, "tools": []},
            "brief": {"canvas": ["neither", 0.9], "request_type": ["order", 0.63], "screen_action": ["none", 0.44],
                      "wants_words": ["act", 0.54], "corrects_last": ["corrects_last", 0.9]},
            "expect": "data-op musica:play", "forbid": []}
    return harness.run_case(case)


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_promise_gets_the_play_act(second_pass_plays, monkeypatch, lang):
    out = _turn(lang, late_card="musica", monkeypatch=monkeypatch)
    assert out.decision == "data-op musica:play", (out.decision, out.reply)
    assert any("segunda pasada" in str(e.get("label")) and "musica:play" in str(e.get("text")) for e in out.events)


@pytest.mark.parametrize("lang", ["en", "es"])
def test_with_no_verdict_naming_a_card_the_pass_gets_nothing(second_pass_plays, monkeypatch, lang):
    out = _turn(lang, late_card="", monkeypatch=monkeypatch)
    assert not [d for d in out.all_decisions if d.startswith("data-op")], (out.decision, out.also)
