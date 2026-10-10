"""«More of those» on the picture viewer is the picture search, whatever tool the model reached for (pass 110, I2).

«cool, show me a few more of those» came right after the F40 photos, whose search was still loading — the model's
window did not hold them yet, so it said «let me pull a few more 27-inch 4K options» and a listing search opened a
SECOND monitors sheet that broke I3, I4 and the S block. The verdict read `imagenes:add` at 0.99. A sure verdict
on the viewer's `add` is more of the search under way (or last made); its `show` is his words, on an empty viewer.
"""
from __future__ import annotations

import pytest

from nucleo.flash import card_commission as cc
from nucleo.flash import image_turn as it


@pytest.fixture
def verdict(monkeypatch, tmp_path):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from nucleo.flash import direct_action as _da, turn_brief as _tb
    state = {"target": ("imagenes:add", 0.99)}

    def read(_brief, key, fallback, *, min_confidence=None):
        if key != _tb.TARGET_KEY:
            return fallback, None
        choice, conf = state["target"]
        return (choice, {"confidence": conf, "used": True}) if conf >= (min_confidence or 0.0) else (fallback, None)
    monkeypatch.setattr(_tb, "read", read)
    monkeypatch.setattr(_da, "from_brief", lambda _b: tuple(state["target"][0].split(":")))
    monkeypatch.setitem(it.LAST_QUERY, "q", "")
    return state


def test_more_of_those_is_more_of_the_search_under_way(verdict):
    it.LAST_QUERY["q"] = "red Ferrari F40"
    got = cc.picture_named_by("cool, show me a few more of those", object())
    assert got == {"query": "red Ferrari F40", "n": it.DEFAULT_N, "more": True}, got


def test_with_nothing_under_way_the_viewer_query_is_more_of(verdict):
    from widgets import store
    store.save("imagenes", {"query": "Crab nebula", "items": [{"url": "u"}]})
    assert cc.picture_named_by("a few more", object())["query"] == "Crab nebula"


def test_an_unsure_verdict_or_another_card_changes_nothing(verdict):
    it.LAST_QUERY["q"] = "red Ferrari F40"
    verdict["target"] = ("imagenes:add", 0.6)
    assert cc.picture_named_by("cool, show me a few more of those", object()) is None
    verdict["target"] = ("results:view", 0.99)
    assert cc.picture_named_by("cool, show me a few more of those", object()) is None


def test_show_searches_only_an_empty_viewer(verdict):
    from widgets import store
    verdict["target"] = ("imagenes:show", 0.99)
    assert cc.picture_named_by("show me a blue lamborghini", object())["query"] == "show me a blue lamborghini"
    store.save("imagenes", {"query": "x", "items": [{"url": "u"}]})
    assert cc.picture_named_by("show me the pictures", object()) is None


def test_the_search_records_what_it_is_looking_for():
    src = open("nucleo/flash/image_turn.py", encoding="utf-8").read()
    i = src.index("async def execute(")
    assert src.index('LAST_QUERY["q"] = q', i) < src.index("_bs.images(", i), "recorded BEFORE the search runs"
