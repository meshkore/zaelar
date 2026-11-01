"""An empty card is filled the way IT declares, read by one door — never by a table of card names (V2-832, audit A13).

The class: the picture viewer and the video catalogue were filled through `TOOL_FILLED = {"imagenes": …}`,
`SEARCH_FILLED = {"youtube": …}` and a `_viewer_empty()` that read the store of the literal `imagenes` — the base card,
never the instance the turn is on. #152 (pass 10 B1) widened that rail. Now each manifest declares `"fill"` and
`nucleo/acts/fill.py` is the one reader: a third card gets the behaviour by declaring it, an instance is judged by its
own view, and a card that declares nothing is never filled.
"""
from __future__ import annotations

import pytest

from nucleo.acts import fill
from nucleo.flash import card_commission as cc

DECLARED = {"imagenes": {"fill": {"tool": "show_images", "filled_by": "items"}},
            "youtube": {"fill": {"action": "search", "key": "query", "filled_by": "searched_at"}},
            "podcasts": {"fill": {"action": "find_episodes", "key": "topic", "filled_by": "episodes"}},
            "agenda": {}}


@pytest.fixture
def cards(monkeypatch):
    from nucleo import truth
    from widgets import runtime
    views: dict = {}
    monkeypatch.setattr(runtime, "get", lambda wid: DECLARED.get(wid))
    monkeypatch.setattr(truth, "widget_view", lambda wid: views.get(wid, {}))
    return views


def test_the_shipped_cards_declare_how_they_fill():
    from widgets import runtime
    assert fill.tool_of("imagenes") == "show_images" and fill.search_of("youtube") == ("search", "query")
    assert runtime.get("imagenes").get("fill") and runtime.get("youtube").get("fill")


def test_a_third_card_fills_by_its_declaration_with_no_engine_edit(cards):
    req = cc.search_to_fill("podcasts", "find episodes about the Apollo missions")
    assert req == {"widget_id": "podcasts", "action": "find_episodes",
                   "payload": {"topic": "find episodes about the Apollo missions"}}
    cards["podcasts"] = {"episodes": [{"title": "Apollo 11"}]}
    assert cc.search_to_fill("podcasts", "find episodes about the Apollo missions") is None, "a full card shows itself"


def test_an_instance_is_judged_by_its_own_view(cards):
    cards["imagenes"] = {"items": []}
    cards["imagenes::2"] = {"items": [{"url": "https://example.com/a.jpg"}]}
    assert fill.is_empty("imagenes") and not fill.is_empty("imagenes::2")
    assert cc.picture_search_for("imagenes::2", "red Ferrari F40") is None, "the instance holds pictures"
    assert (cc.picture_search_for("imagenes", "red Ferrari F40") or {}).get("query") == "red Ferrari F40"


def test_a_card_that_declares_nothing_is_never_filled(cards):
    assert not fill.is_empty("agenda") and fill.tool_of("agenda") == "" and fill.search_of("agenda") is None
    assert cc.search_to_fill("agenda", "what do I have on Monday") is None
    assert cc.picture_search_for("agenda", "what do I have on Monday") is None


def test_no_card_is_named_in_the_door():
    import inspect
    src = inspect.getsource(cc) + inspect.getsource(fill)
    code = "\n".join(line.split("#")[0] for line in src.splitlines() if not line.strip().startswith(("#", "`", "«")))
    assert '"imagenes"' not in code and '"youtube"' not in code
