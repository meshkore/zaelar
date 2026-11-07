"""A sure «no canvas verb» verdict outranks the word guard that turns the model's tool into a show.

Measured on the operator's engine (2026-11-07, trace T1·b0e8): «Busca en la web a qué hora abre hoy el Museo del Prado
y dímelo». The model called `web_search`. The deterministic show guard read «abre» (the museum OPENS) as an order to
open a card and «la web» as the browser's alias, nulled the search and showed the browser card — while the brief had
read the whole sentence as `canvas = neither` at 1.00. The card was then read back (it only shows its controls) and
the turn answered «I can't see the opening hours». A sure `neither` now keeps the model's tool; below the veto floor
the guard works as before.
"""
from __future__ import annotations

import asyncio
import inspect
import types

import pytest

from nucleo.flash import post_stream as P          # first: `canvas_verdict` ↔ `direct_action` load through it
from nucleo.flash import post_stream_acts as A
from nucleo.acts import canvas_verdict
from nucleo.turn import brief as tb

SAID = {"es": "Busca en la web a qué hora abre hoy el Museo del Prado y dímelo.",
        "en": "Look up on the web what time the Prado opens today and tell me."}


class _Stop(Exception):
    pass


def _brief(choice: str, confidence: float):
    return tb.revived({"result": {"canvas": {"choice": choice, "confidence": confidence}}})


def _run(monkeypatch, said, brief):
    from nucleo.flash import card_commission, post_stream_settle
    from nucleo.request import stop
    from nucleo.turn import route_by_verdict
    monkeypatch.setattr(stop, "steer", lambda *a, **k: None)
    monkeypatch.setattr(post_stream_settle, "no_new_errand_for_a_bound_answer", lambda *a, **k: None)
    monkeypatch.setattr(route_by_verdict, "owns", lambda *a, **k: False)
    monkeypatch.setattr(card_commission, "picture_named_by", lambda *a, **k: None)
    monkeypatch.setattr(P._show_target, "show_from_verb", lambda *a, **k: (None, "none"))
    presented: list = []
    monkeypatch.setattr(P._cvis, "present", lambda wid, **k: presented.append(wid) or True)   # the canvas would accept
    monkeypatch.setattr(P._cvis, "card_is_open", lambda wid, **k: False)

    async def _halt(*a, **k):
        raise _Stop
    monkeypatch.setattr(P._resume_turn, "before_fragment_guard", _halt)
    guard_calls: list = []
    events: list = []
    kw = {n: None for n in inspect.signature(A.complete_the_acts).parameters}
    search_req, escalate_req, acted = {"v": {"query": said}}, {"v": None}, {"widget": False}
    kw.update(_show_guard_target=lambda *a, **k: guard_calls.append(a) or "navegador", _brief=brief,
              _router=types.SimpleNamespace(operator_words=lambda o, t: o),
              brain=types.SimpleNamespace(_window=[], _last_action=""), text=said, operator_text=said,
              spoken=["Voy a mirarlo."], emit=lambda *a, **k: events.append(a), send=lambda *a, **k: None,
              search_req=search_req, escalate_req=escalate_req, acted=acted, data_done={"v": False, "ops": []},
              images_req={"v": None}, listing_req={"v": None}, music_req={"v": None}, read_req={"v": None})
    with pytest.raises(_Stop):
        asyncio.run(A.complete_the_acts(**kw))
    return search_req, acted, presented, guard_calls, events


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_sure_neither_keeps_the_search_and_shows_no_card(monkeypatch, lang):
    search_req, acted, presented, guard_calls, events = _run(monkeypatch, SAID[lang], _brief("neither", 1.0))
    assert search_req["v"] is not None, "the model's search was nulled against a sure «no canvas verb»"
    assert not acted["widget"] and presented == [] and guard_calls == []
    assert any("tool stands" in str(e[1]) for e in events if len(e) > 1)


@pytest.mark.parametrize("brief", [None, ("neither", 0.6), ("show", 1.0)])
def test_without_a_sure_neither_the_guard_still_swaps(monkeypatch, brief):
    search_req, acted, presented, _, _ = _run(monkeypatch, SAID["es"], _brief(*brief) if brief else None)
    assert search_req["v"] is None and acted["widget"] and presented == ["navegador"]


def test_sure_no_canvas_reads_the_veto_floor():
    assert canvas_verdict.sure_no_canvas(_brief("neither", 0.85))
    assert not canvas_verdict.sure_no_canvas(_brief("neither", 0.84))
    assert not canvas_verdict.sure_no_canvas(_brief("show", 1.0))
    assert not canvas_verdict.sure_no_canvas(None)
