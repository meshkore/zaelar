"""The show guard swaps the model's tool for a card only when the card ends up on screen.

Measured on a phone: «ponme un poquito de música… mira a ver si la localizas y me pones algo de ella». The model
called `web_search` and said it would put her on. The deterministic show guard read «pon» as «show me a card», found
an old results card and nulled the search; the canvas door then refused that show (`verdict-against`, canvas=neither).
No search, no card, the promise already spoken: a turn that did nothing. A refused show now leaves the tool alone.
"""
from __future__ import annotations

import asyncio
import inspect
import types

import pytest

from nucleo.flash import post_stream as P
from nucleo.flash import post_stream_acts as A

SAID = {"es": "Mira a ver si localizas a la cantante de la serie y me pones algo de ella.",
        "en": "See if you can find the singer from the show and put on something of hers."}


class _Stop(Exception):
    pass


def _run(monkeypatch, said, *, shown, already_open=False):
    from nucleo.flash import card_commission, post_stream_settle
    from nucleo.request import stop
    from nucleo.turn import route_by_verdict
    monkeypatch.setattr(stop, "steer", lambda *a, **k: None)
    monkeypatch.setattr(post_stream_settle, "no_new_errand_for_a_bound_answer", lambda *a, **k: None)
    monkeypatch.setattr(route_by_verdict, "owns", lambda *a, **k: False)
    monkeypatch.setattr(card_commission, "picture_named_by", lambda *a, **k: None)
    presented: list = []
    monkeypatch.setattr(P._cvis, "present", lambda wid, **k: presented.append(wid) or shown)
    monkeypatch.setattr(P._cvis, "card_is_open", lambda wid, **k: already_open)

    async def _halt(*a, **k):        # everything after the guard is another section's business
        raise _Stop
    monkeypatch.setattr(P._resume_turn, "before_fragment_guard", _halt)
    events: list = []
    kw = {n: None for n in inspect.signature(A.complete_the_acts).parameters}
    search_req, escalate_req = {"v": {"query": said}}, {"v": None}
    acted = {"widget": False}
    kw.update(_show_guard_target=lambda *a, **k: "results::089b85-2", _brief=None, _router=types.SimpleNamespace(
                  operator_words=lambda o, t: o),
              brain=types.SimpleNamespace(_window=[], _last_action=""), text=said, operator_text=said,
              spoken=["Voy a buscarla y te la pongo."], emit=lambda *a, **k: events.append(a),
              send=lambda *a, **k: None, search_req=search_req, escalate_req=escalate_req, acted=acted,
              data_done={"v": False, "ops": []}, images_req={"v": None}, listing_req={"v": None},
              music_req={"v": None}, read_req={"v": None})
    with pytest.raises(_Stop):
        asyncio.run(A.complete_the_acts(**kw))
    return search_req, acted, presented, events


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_show_the_canvas_refuses_keeps_the_search(monkeypatch, lang):
    search_req, acted, presented, events = _run(monkeypatch, SAID[lang], shown=False)
    assert presented == ["results::089b85-2"]
    assert search_req["v"] is not None, "the model's search was nulled for a card that never appeared"
    assert not acted["widget"]
    assert any("tool stands" in str(e[1]) for e in events if len(e) > 1)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_show_that_lands_still_replaces_the_spurious_tool(monkeypatch, lang):
    search_req, acted, _, _ = _run(monkeypatch, SAID[lang], shown=True)
    assert search_req["v"] is None and acted["widget"]


def test_a_card_already_on_screen_counts_as_shown(monkeypatch):
    search_req, acted, _, _ = _run(monkeypatch, SAID["es"], shown=False, already_open=True)
    assert search_req["v"] is None and acted["widget"]
