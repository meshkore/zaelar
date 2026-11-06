"""The card an order names is read from BOTH catalogue twins (`catalog_widget` and `catalog_closed`).

With cards open the brief asks the closed-card catalogue under its own key. Measured on a phone: «mira a ver si la
localizas y me pones algo de ella» read `catalog_closed=musica` 0.94 and `request_type=order`; the turn searched for the
singer, and the order after the search (`repair_after_lookup.order_card_after_search`) found no card to call because
`named_card` only read `catalog_widget`. The canvas arbiter had the same blind spot (demo sandbox 2026-11-05, F1).
"""
from __future__ import annotations

import threading

import pytest

from nucleo.acts import repair_after_lookup as ral
from nucleo.flash import build_decision as bd
from nucleo.flash import direct_action
from nucleo.turn import brief as tb


def _brief(**result) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": ["youtube"], "result": result}


@pytest.fixture(autouse=True)
def _no_screen_action(monkeypatch):
    monkeypatch.setattr(direct_action, "from_brief", lambda brief: ("", ""))
    monkeypatch.setattr(bd, "card_mass", lambda brief: "")


def test_a_sure_closed_catalogue_names_the_card():
    assert bd.named_card(_brief(**{tb.CATALOG_CLOSED_KEY: {"choice": "musica", "confidence": 0.94}})) == "musica"


def test_the_open_catalogue_still_answers_when_it_was_the_one_asked():
    assert bd.named_card(_brief(**{tb.CATALOG_KEY: {"choice": "agenda", "confidence": 0.93}})) == "agenda"


def test_an_unsure_closed_catalogue_names_nothing():
    assert bd.named_card(_brief(**{tb.CATALOG_CLOSED_KEY: {"choice": "musica", "confidence": 0.30}})) == ""


@pytest.mark.parametrize("answer", ["La cantante es Natalia Lafourcade.", "The singer is Natalia Lafourcade."],
                         ids=["es", "en"])
def test_a_sure_order_after_a_search_reaches_the_music_card(answer):
    brief = _brief(**{tb.REQUEST_KEY: {"choice": "order", "confidence": 0.99},
                      tb.CATALOG_CLOSED_KEY: {"choice": "musica", "confidence": 0.94}})
    assert ral.order_card_after_search(brief, answer) == "musica"
