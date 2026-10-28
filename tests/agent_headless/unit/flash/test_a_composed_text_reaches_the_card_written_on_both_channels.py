"""A text the commission pass chooses to WRITE reaches the card written, on the text channel as on the voice (2026-10-27).

docs-single-recipe-not-a-list__us: the text channel recorded the pass's `compose_into_card` as
`documento:show {title, _compose}` — no body. Executed, the sheet refused it («'body' vacío»), a repair rewrote it a
moment later, and the reply had already read the empty sheet: «I don't have the recipe text itself — just the
title». The voice rail composes first (`compose_rung.run`); the text channel now does the same before the call
reaches the card, and a composition that fails leaves the call as it was so the card's own refusal is said.
"""
from __future__ import annotations

import asyncio

from nucleo.flash import compose_rung as CR
from nucleo.flash import card_commission as CC

RECIPE = "## Ingredients\n400 g spaghetti, 150 g guanciale, 4 yolks, pecorino, pepper."


def test_a_compose_call_is_written_before_it_reaches_the_card(monkeypatch):
    seen = {}

    async def _compose(got, operator_text, spec, window=None):
        seen.update(got)
        return RECIPE

    monkeypatch.setattr(CR, "compose", _compose)
    out = asyncio.run(CC.written({"title": "Spaghetti alla Carbonara", "_compose": True,
                                   "_brief": "the classic Roman recipe"}, "Give me the carbonara recipe."))
    assert out == {"title": "Spaghetti alla Carbonara", "body": RECIPE}
    assert seen == {"title": "Spaghetti alla Carbonara", "brief": "the classic Roman recipe"}


def test_any_other_call_passes_through_untouched():
    pl = {"title": "X", "body": "already written"}
    assert asyncio.run(CC.written(pl, "q")) is pl
    assert asyncio.run(CC.written({"symbol": "AAPL"}, "q")) == {"symbol": "AAPL"}


def test_a_failed_composition_leaves_the_call_for_the_card_to_refuse(monkeypatch):
    async def _empty(*a, **k):
        return ""

    monkeypatch.setattr(CR, "compose", _empty)
    pl = {"title": "X", "_compose": True}
    assert asyncio.run(CC.written(pl, "q")) == pl


def test_the_executor_and_the_commission_rung_are_wired():
    src = open("nucleo/flash/widget_data_turn.py", encoding="utf8").read()
    assert "pl = await _cc.written(" in src
