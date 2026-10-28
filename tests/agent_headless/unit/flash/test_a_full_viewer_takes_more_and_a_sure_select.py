"""Pictures on a FULL viewer: «the second one» under a sure `select` is not asked, and «more of those» adds
(refactor2710-99, bank class B).

`live-i3-second-photo-after-a-report` («open the second one», 7 → 3): the verdict read `imagenes:select` at 0.96,
the model called `select` with `item: "Red Ferrari F40"` — a title all eight pictures share — and the card door
asked «Which one exactly? I have 1. Red Ferrari F40 photo 1, 2. …». A sure verdict said the card and the act were
right; the doubt was only the model's reference, and his own sentence names one row (`card.his_row`).

`live-i2-more-photos-after-a-report` («cool, show me a few more of those», 7 → 0): the model called `show_images`
for the same search the viewer already held, without `more`, and the viewer was REPLACED. The same search asked
again over a viewer that holds it is «more» — read from the viewer's own `query`, never from his words.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo.acts import card
from nucleo.turn import brief as _tb

_ITEMS = [{"title": f"Red Ferrari F40 photo {i}", "url": f"https://img.example.com/f40-{i}.jpg",
           "thumb": f"https://img.example.com/f40-{i}-t.jpg", "site": "img.example.com", "w": 1600, "h": 900}
          for i in range(1, 9)]


@pytest.fixture
def viewer(monkeypatch):
    from widgets import store
    held = {"imagenes": {"items": list(_ITEMS), "query": "red ferrari f40", "source": "web"}}
    monkeypatch.setattr(store, "load", lambda wid, default=None, **k: held.get(wid, default or {}))
    return held


def _brief(choice: str, conf: float):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": ["results::t135", "imagenes"],
            "result": {_tb.TARGET_KEY: {"choice": choice, "confidence": conf}}}


# ── «the second one» under a sure select ─────────────────────────────────────────────────────────────────────

def test_the_models_ambiguous_reference_was_the_doubt(viewer):
    from widgets import refs
    assert refs.resolve("imagenes", "select", "", {"item": "Red Ferrari F40"}).needs == "ambiguous"


@pytest.mark.parametrize("said", ["open the second one", "abre la segunda"])
def test_a_sure_select_takes_the_row_his_words_name(viewer, said):
    res = card.his_row(_brief("imagenes:select", 0.96), "imagenes", "select", {"item": "Red Ferrari F40"}, said)
    assert res is not None and res.ok and str(res.payload.get("item")) == "2", res


@pytest.mark.parametrize("choice,conf", [("imagenes:select", 0.7), ("imagenes:next", 0.96), ("results:select", 0.96)])
def test_an_unsure_or_other_verdict_leaves_the_question(viewer, choice, conf):
    assert card.his_row(_brief(choice, conf), "imagenes", "select", {"item": "Red Ferrari F40"},
                        "open the second one") is None


# ── «more of those» over a full viewer ───────────────────────────────────────────────────────────────────────

def _run(monkeypatch, query: str, more: bool = False) -> list:
    from nucleo.flash import image_turn
    from search import browser
    from widgets import server_api
    calls: list = []

    async def _images(q, n):
        return {"items": [{"title": f"new {i}", "url": f"https://img.example.com/new-{i}.jpg"} for i in range(n)],
                "source": "web"}

    async def _brain_action(wid, action, payload):
        calls.append((wid, action))
        return {"ok": True, "added": 3, "count": 11}

    monkeypatch.setattr(browser, "images", _images)
    monkeypatch.setattr(server_api, "brain_action", _brain_action)
    asyncio.run(image_turn.execute(query, 4, more))
    return calls


@pytest.mark.parametrize("query", ["red ferrari f40", "Red Ferrari  F40"])
def test_the_same_search_over_the_viewer_adds(viewer, monkeypatch, query):
    assert _run(monkeypatch, query) == [("imagenes", "add")], "the viewer was replaced with the search it held"


def test_a_new_search_still_replaces(viewer, monkeypatch):
    assert _run(monkeypatch, "blue lamborghini") == [("imagenes", "show")]


def test_an_empty_viewer_shows(monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "load", lambda wid, default=None, **k: default or {})
    assert _run(monkeypatch, "red ferrari f40") == [("imagenes", "show")]
