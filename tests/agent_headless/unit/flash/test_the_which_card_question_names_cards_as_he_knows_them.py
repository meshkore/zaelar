"""The «which card?» question names the cards as he knows them, never by id (V2-781, 2026-10-11).

Both rounds asked «¿Cuál exactamente? Tengo musica, youtube.» / «Which one exactly? I have musica, youtube.» — raw
folder ids in the operator's ear. `which_card`'s labels start with the id; `card_receipt.display_label` shows that id as
the card's translated catalogue name («Música», «Music», «YouTube») and keeps the live rail after it.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import card_receipt as R

BOTH = ["youtube", "musica"]


def _brief(open_ids=BOTH) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids), "result": {}}


@pytest.fixture(autouse=True)
def _screen(monkeypatch):
    from memory import api as _memapi
    monkeypatch.setattr(_memapi, "state", lambda *a, **k: {"open_widgets": list(BOTH)})
    from nucleo.flash import named_target as NT
    NT._PARKED.clear()


def test_a_label_keeps_its_rail_and_shows_the_name():
    assert R.display_label("youtube — pausado", "es") == "YouTube — pausado"
    assert R.display_label("musica", "es") == "Música"
    assert R.display_label("musica", "en") == "Music"
    assert R.display_label("") == ""


@pytest.mark.parametrize("lang,music", [("es", "Música"), ("en", "Music")])
def test_the_question_says_the_display_names(monkeypatch, lang, music):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from nucleo.flash import frontend as FE
    cd = FE.card_decision("musica", "volume_down", brief=_brief(), ask_phrase="? {cands}")
    assert cd["ask"], cd
    assert music in cd["ask"] and "YouTube" in cd["ask"], cd["ask"]
    assert "musica" not in cd["ask"] and "youtube" not in cd["ask"], cd["ask"]
