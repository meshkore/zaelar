"""A status sentence, and a wait's step line, never say a worker note about OUR plumbing (node 2.702).

search-buy-vinyl ES (2026-10-14, sandbox 104614-es): «Así va todo: Comprar vinilo The Dark Side of the Moon — Criterios
duros registrados y fuentes abiertas (eBay + Wallapop).» The worker was reporting that it filled our sheet's hard-
criteria column. The step line already dropped notes about the sheet contract; the status line read only the
language. One reader now serves both (`speakable_note`).
"""
from __future__ import annotations

import threading

import pytest

from nucleo import dispatch
from nucleo.flash import speakable_note as S
from nucleo.flash import step_line
from nucleo.turn import errands_of_a_turn as E

ERRAND = "Búscame el vinilo original de 'The Dark Side of the Moon' en buen estado por menos de 60 euros."
PLUMBING = "Criterios duros registrados y fuentes abiertas (eBay + Wallapop)"
STEP = "Wallapop responde y acepta el filtro de precio; extrayendo anuncios"


def _brief():
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {"wants_words": {"choice": "tell", "confidence": 0.99, "probs": {"tell": 0.99}}},
            "_call_id": "t", "turn_id": "t", "open_ids": []}


@pytest.fixture
def spanish(monkeypatch):
    monkeypatch.setattr("i18n.langs.current_code", lambda: "es")
    return monkeypatch


@pytest.mark.parametrize("note", [PLUMBING, "Hard criteria registered, sources open", "Contrato de la hoja leído",
                                  "mirando «results::018201-ls1»"])
def test_a_note_about_our_plumbing_is_not_speakable(note):
    assert S.plumbing(note)
    assert not S.speakable(note, "es")


def test_the_status_line_says_under_way_instead(spanish):
    spanish.setattr(dispatch, "pending_summaries", lambda: [
        {"id": "2", "request": ERRAND, "phase": "", "note": PLUMBING, "waiting_on": ""}])
    line = E.status_owed("¿Alguna novedad?", _brief())
    assert "Criterios duros" not in line and "en marcha" in line, line


def test_a_note_about_his_errand_is_still_said(spanish):
    spanish.setattr(dispatch, "pending_summaries", lambda: [
        {"id": "2", "request": ERRAND, "phase": "", "note": STEP, "waiting_on": ""}])
    assert STEP in E.status_owed("¿Alguna novedad?", _brief())


def test_the_step_line_reads_the_same_rule():
    assert step_line.candidates({"note": PLUMBING, "phase": "", "plan": []}, "es") == []
    assert step_line.candidates({"note": STEP, "phase": "", "plan": []}, "es") == [STEP]


def test_an_engine_phase_never_reaches_an_english_status(monkeypatch):
    monkeypatch.setattr("i18n.langs.current_code", lambda: "en")
    assert E.errand_state({"phase": "leyendo la ficha del vendedor", "note": ""}).startswith("under way")
