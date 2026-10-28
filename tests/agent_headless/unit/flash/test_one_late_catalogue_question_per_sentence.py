"""V2-794 — the late catalogue question is asked ONCE per sentence; its answer is read by every repair of the turn.

Measured on a live session: «Crea una lista de 40 canciones» — the promise repair asked the catalogue and got
`musica` (0.44, 197 ms); a second repair (the «promised to look» one) asked the SAME question about the SAME words,
that trip timed out at 3.5 s, and its «none» was the only answer it saw. One question, one answer, read twice — and
a timeout never replaces an answer already paid for. An unsure answer stays below each caller's floor: it is kept
as evidence, never acted on (the repair floor exists because a 0.63 guess once wrote into the wrong card).
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo.flash import card_commission as cc


@pytest.fixture
def catalogue(monkeypatch):
    from nucleo import jev
    from nucleo.turn import brief as turn_brief
    calls: list = []
    answer = {"v": {"choice": "musica", "confidence": 0.44}}
    monkeypatch.setattr(turn_brief, "catalog_question", lambda: {"instructions": "i", "criteria": {"musica": "m"}})
    monkeypatch.setattr(jev, "choose_sync", lambda *a, **k: calls.append(a) or answer["v"])
    return calls, answer


def _none_brief() -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": ["agenda"],
            "result": {"screen_action": {"choice": "none", "confidence": 0.95}}}


def test_the_second_reader_gets_the_first_answer_without_a_second_trip(catalogue):
    calls, _answer = catalogue
    from nucleo.flash import second_pass
    assert cc.named_or_catalogue(_none_brief(), "Crea una lista de 40 canciones") == "", "0.44 is under the floor"
    assert cc.late_catalogue("Crea una lista de 40 canciones") == ("musica", 0.44), "the evidence is kept"
    asyncio.run(second_pass._card_the_catalogue_names("crea una lista de 40  canciones"))
    assert len(calls) == 1, f"one question per sentence, asked {len(calls)} times"


def test_a_timed_out_trip_is_not_remembered_as_an_answer(catalogue):
    calls, answer = catalogue
    answer["v"] = {"choice": "none", "confidence": 0.0, "error": "TimeoutError"}
    assert cc.late_catalogue("Haz una lista de 20 películas") == ("none", 0.0)
    answer["v"] = {"choice": "youtube", "confidence": 0.81}
    assert cc.late_catalogue("Haz una lista de 20 películas") == ("youtube", 0.81), "a failure is asked again"
    assert len(calls) == 2


def test_a_sure_answer_still_names_the_card(catalogue):
    _calls, answer = catalogue
    answer["v"] = {"choice": "agenda", "confidence": 0.9}
    assert cc.named_or_catalogue(_none_brief(), "Apunta la cena del sábado") == "agenda"
