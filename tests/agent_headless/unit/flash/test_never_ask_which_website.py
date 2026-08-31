"""V2-147 (`find-theatre-tickets__es`) — asked which website despite the engine having the answer.

Turn 1: “Do you have a favorite website or agency… or would you rather I search the options?”. Turn 2, the
operator: “I don’t have a favorite website, search wherever there are options”. Turn 8, zaelar again: “Which
website or platform do you want me to go to search for the tickets?”. The judge marks it `alta`, and the watchdog
caught it live.

And the engine DID have the answer since V2-132: `site_catalog` has one entry per type of assignment, and the
worker receives it attached to the task — measured here as, “START with Entradas.com”. What was missing was that
the catalog had never been visible to the FlashBrain prompt, so to the brain “which website” seemed like data that
only the operator has. It is the same pattern as throughout the batch: the capability exists, and it is invisible
from where the decision is made.

The catalog is intentionally not listed in the prompt — that would be O(N) on every turn (V2-085), and it is
enough for it to know that it exists.
"""
from __future__ import annotations

import pytest

from nucleo import dispatch
from nucleo import dispatch_prompts
from nucleo.flash import prompt
from nucleo.flash import router_guards as g
from nucleo.flash import site_catalog as sc


ASK = "Consígueme dos entradas para el musical de El Rey León en Madrid para el sábado."


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from memory import db as memdb
    from memory import embeddings as mememb
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()
    mememb.reset()


def test_the_brain_is_told_it_already_has_a_destination(fresh_db):
    system, _ = prompt.build_flash_system()
    assert "NO le preguntes EN QUÉ WEB" in system
    assert "sitio de confianza por tipo de encargo" in system


def test_and_it_is_told_WITHOUT_listing_the_catalog(fresh_db):
    """The catalog is per-category and grows; pasting it into every turn is the O(N) mistake V2-085 measured.
    The brain only needs to know a destination exists — the worker is the one that opens it."""
    system, _ = prompt.build_flash_system()
    for entry in sc.SITE_CATALOG["es"].values():
        assert entry.url not in system


def test_the_engine_really_does_have_the_answer_it_was_asking_for(monkeypatch):
    """The rule would be a lie if there were no destination behind it. Pin it for this exact errand."""
    from voice.engine.core import langs
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    assert sc.category_of(ASK) == "event_tickets"
    assert dispatch._classify_kind(ASK) == "web"
    assert g._needs_real_work(ASK) is True
    lead = [l for l in dispatch_prompts._web_prompt(ASK, "").splitlines()
            if "ESTA TAREA es de categoría" in l]
    assert lead and "entradas.com" in lead[0].lower()


def test_asking_for_what_only_the_operator_knows_is_still_right(fresh_db):
    """The rule is narrow: the showtime, the day, his preference are his to give — only the SITE is ours."""
    system, _ = prompt.build_flash_system()
    assert "pide solo lo que NO puedes averiguar" in system
    assert "PÍDELO — preguntar es la respuesta" in system
