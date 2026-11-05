"""The catalogue question about a CLOSED card is asked in the turn's one Jev trip, never after the stream (V2-851 F5).

V2-794 measured the late question asked twice about the same words (one trip timed out at 3.5 s and its «none»
replaced an answer already paid for) and kept one answer per sentence. V2-851 F5 removed the late trip altogether:
while cards are open the brief asks the catalogue too, under its own key (`catalog_closed`, so the readers of
`catalog_widget` see nothing new), and `named_or_catalogue` only reads it. Zero model calls after the main stream.
An unsure answer stays below the caller's floor: kept as evidence, never acted on.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import card_commission as cc
from nucleo.turn import brief as tb


@pytest.fixture
def no_trip(monkeypatch):
    from nucleo import jev
    calls: list = []
    monkeypatch.setattr(jev, "choose_sync", lambda *a, **k: calls.append(a) or {"choice": "musica", "confidence": 0.99})
    return calls


def _brief(closed=None) -> dict:
    ev = threading.Event()
    ev.set()
    res = {"screen_action": {"choice": "none", "confidence": 0.95}}
    if closed:
        res[tb.CATALOG_CLOSED_KEY] = {"choice": closed[0], "confidence": closed[1]}
    return {"event": ev, "turn_id": "t", "open_ids": ["agenda"], "result": res}


def test_the_closed_card_is_read_from_the_brief_with_no_trip(no_trip):
    assert cc.named_or_catalogue(_brief(("agenda", 0.9)), "Apunta la cena del sábado") == "agenda"
    assert no_trip == [], "no Jev call after the stream"


def test_an_unsure_reading_names_nothing(no_trip):
    assert cc.named_or_catalogue(_brief(("musica", 0.44)), "Crea una lista de 40 canciones") == ""
    assert no_trip == []


def test_no_reading_names_nothing_and_asks_nothing(no_trip):
    assert cc.named_or_catalogue(_brief(), "Crea una lista de 40 canciones") == ""
    assert no_trip == [], "a brief without the answer is not a reason for a second trip"


def test_the_brief_asks_it_only_while_cards_are_open(monkeypatch):
    monkeypatch.setattr(tb, "catalog_question", lambda: {"instructions": "i", "criteria": {"agenda": "a"}})
    monkeypatch.setattr(tb, "target_question", lambda ids: {"instructions": "t", "criteria": {"none": "n"}} if ids else None)
    open_qs = tb.build("Apunta la cena", open_ids=["agenda"])
    assert tb.CATALOG_CLOSED_KEY in open_qs and tb.CATALOG_KEY not in open_qs
    none_qs = tb.build("Apunta la cena", open_ids=[])
    assert tb.CATALOG_KEY in none_qs and tb.CATALOG_CLOSED_KEY not in none_qs


def test_the_late_trip_is_gone():
    """The disarm: `late_catalogue` sent its own `choose_sync` from the post-stream chain."""
    src = open("nucleo/flash/card_commission.py", encoding="utf-8").read()
    assert "choose_sync" not in src and "late_catalogue(" not in src
