"""An order on the EMPTY picture viewer is first its search (V2-831 pass 10, B1 on v3.107).

The model called `imagenes:wallpaper {query}` with nothing on screen. The wallpaper action's declared payload is an
`item` the viewer already holds, so the card refused; the refusal pass may only re-issue the same action, and no
search ever ran — B2/B3 cascaded. A model call on the empty viewer that carries what to look for is the picture
search; on a viewer that holds pictures it stays the card's own act. Bench: `demo-b1-wallpaper-with-a-query-…`.
"""
from __future__ import annotations

import pytest

from nucleo.flash import card_commission as cc

Q = "Cosmic Eye in the Sky Tyler Young Orion Nebula"
TEXT = "find me the wallpaper cosmic eye in the sky by tyler young, the orion nebula"


@pytest.mark.parametrize("empty,want", [(True, True), (False, False)])
def test_a_wallpaper_with_a_query_is_the_search_only_on_the_empty_viewer(monkeypatch, empty, want):
    monkeypatch.setattr(cc, "_viewer_empty", lambda: empty)
    got = cc.picture_search_for_empty_show("imagenes", "wallpaper", {"query": Q}, TEXT)
    assert bool(got) is want, got
    if want:
        assert got["query"].startswith(Q) and got["more"] is False


def test_another_card_is_never_a_picture_search(monkeypatch):
    monkeypatch.setattr(cc, "_viewer_empty", lambda: True)
    assert cc.picture_search_for_empty_show("agenda", "add_meeting", {"query": Q}, TEXT) is None


def test_an_act_with_nothing_to_look_for_is_left_to_the_card(monkeypatch):
    monkeypatch.setattr(cc, "_viewer_empty", lambda: True)
    assert cc.picture_search_for_empty_show("imagenes", "next", {}, "next one") is None
    assert cc.picture_search_for_empty_show("imagenes", "wallpaper", {"item": "2"}, "the second as wallpaper") is None
