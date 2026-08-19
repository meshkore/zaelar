"""V2-147 (`find-theatre-tickets__es`) — preguntó en qué web, teniendo el motor la respuesta.

Turno 1: «¿tienes una web o agencia favorita… o prefieres que busque las opciones?». Turno 2, el operador: «No
tengo ninguna web favorita, busca donde haya opciones». Turno 8, zaelar otra vez: «¿a qué web o plataforma
quieres que entre a buscar las entradas?». El juez lo marca `alta` y el watchdog lo cazó en vivo.

Y el motor SÍ tenía la respuesta desde V2-132: `site_catalog` lleva una entrada por tipo de encargo y el worker
la recibe pegada a la tarea — medido aquí, «EMPIEZA por Entradas.com». Lo que faltaba es que el catálogo nunca
ha estado a la vista del prompt del FlashBrain, así que para el cerebro «en qué web» parecía un dato que solo
tiene el operador. Misma forma que lleva toda la tanda: la capacidad existe, y es invisible desde donde se
decide.

No se lista el catálogo en el prompt a propósito — sería O(N) en cada turno (V2-085) y basta con que sepa que
existe.
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
