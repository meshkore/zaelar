"""V2-475 — a delivery guarantee that only knows Spanish is a defect for everyone else.

Measured on `find-best-hotel-city__us` (2026-08-28): the English half of the board delivered worse than the
Spanish one, and this whole family is why. Every gate and every sentence in `delivery.py` was written against
Spanish wording, which fails in BOTH directions at once and neither of them looks like a bug from the outside:

  · the stall backstop never fired at all in English — its door (`_WAITING_REPLY_RE`) had no English form, so
    «let me nudge the search» over a task stuck for three minutes sailed through as if nothing were wrong;
  · the sheet backstop DID fire, and glued a Spanish paragraph onto an English reply — the guarantee turning
    into the very thing it exists to prevent.

The tests below hold both halves for both languages, because fixing one direction and not the other is how
this family regresses: an English gate added without an English sentence produces Spanish output ON PURPOSE.
"""
from __future__ import annotations

import pytest

from nucleo.flash import delivery as D

ROWS = ["Drury Plaza Hotel — $330", "Best Western Plus St. Christopher — $317"]
EN_WAIT = "I'll let you know as soon as I have something. Let me nudge the search."
ES_WAIT = "Te aviso en cuanto tenga algo."


@pytest.fixture
def hablando_en(monkeypatch):
    """Speak to the operator in a given language, the same way the engine decides it."""
    def _set(code: str):
        monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: code)
    return _set


def test_an_english_stall_is_not_silent(hablando_en):
    """The defect itself: three minutes stuck, and the English operator was told nothing."""
    hablando_en("en")
    out = D.stalled_task_backstop(EN_WAIT, "hotel in New Orleans", 3, "sin_paso")
    assert out, "una espera en inglés sobre un atasco medido no puede salir muda"
    assert "3 min" in out and "stuck" in out.lower()


def test_the_english_stall_sentence_is_english(hablando_en):
    hablando_en("en")
    out = D.stalled_task_backstop(EN_WAIT, "hotel", 4, "callada")
    assert "atascada" not in out and "¿" not in out


def test_english_delivery_does_not_arrive_in_spanish(hablando_en):
    """The other half: the rows were delivered, but in a language the operator did not ask for."""
    hablando_en("en")
    out = D.sheet_delivery_backstop(EN_WAIT, ROWS, "", "hotel New Orleans")
    assert "Drury" in out, "las filas tienen que seguir entregándose"
    for spanish in ("hoja de resultados", "candidatos", "de hecho"):
        assert spanish not in out


def test_spanish_keeps_speaking_spanish(hablando_en):
    """The guard against the obvious regression: making it work in English by breaking Spanish."""
    hablando_en("es")
    assert "hoja de resultados" in D.sheet_delivery_backstop(ES_WAIT, ROWS, "", "hotel")
    assert "atascada" in D.stalled_task_backstop(ES_WAIT, "hotel", 3, "sin_paso")


def test_an_english_reply_that_already_says_it_is_stuck_is_not_told_twice(hablando_en):
    """The English half of «it already says it»: without it, the sentence lands behind a reply that just
    said the same thing — the broken-record failure this family has paid for once already."""
    hablando_en("en")
    ya = "I'll keep you posted, but honestly it looks stuck — no progress for a while."
    assert D.stalled_task_backstop(ya, "hotel", 3, "sin_paso") == ""


def test_a_language_the_engine_cannot_read_still_delivers(monkeypatch):
    """Fail-safe: if the language reader raises, delivery still happens (in the default tongue). A guarantee
    that depends on an import is not a guarantee."""
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert "Drury" in D.sheet_delivery_backstop(ES_WAIT, ROWS, "", "hotel")
