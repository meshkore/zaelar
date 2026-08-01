"""Tests de nucleo/flash/memory_cache.py (V2-011 · T114) — el bloque de memoria se cachea FUERA del turno.

Invariantes: (a) `get()` compone el bloque de ESTADO desde `memory.state()` y lo cachea; (b) NUNCA dispara el
retriever (`memory.query`) — eso es on-demand y fuera del loop (T115/T116); (c) se invalida con `memory.updated`.
"""
import asyncio

import pytest

from memory import api as memapi
from memory import db as memdb
from nucleo.flash import memory_cache


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    memory_cache.reset()
    yield
    memory_cache.reset()
    memdb.reset_db()


def test_get_caches_state_block(fresh_db):
    memapi.set_state({"operator_name": "Ricart", "treatment": "directo"})
    block, op = memory_cache.get()
    assert op == "Ricart"
    # V2-027: el bloque es el ESTADO compuesto (misión QUIÉN ERES + situacional) de memory.compose_state.
    assert "Ricart" in block and "directo" in block and "QUIÉN ERES" in block


def test_get_never_fires_the_retriever(fresh_db, monkeypatch):
    """El bloque cacheado sale SOLO de state(); tocar memory.query() sería meter el retriever en el turno."""
    calls = {"n": 0}
    real_query = memapi.query

    def _spy(*a, **k):
        calls["n"] += 1
        return real_query(*a, **k)

    monkeypatch.setattr(memapi, "query", _spy)
    memapi.set_state({"operator_name": "Ana"})
    memory_cache.get()
    memory_cache.get()
    assert calls["n"] == 0


def test_invalidated_by_memory_updated(fresh_db):
    memapi.set_state({"operator_name": "Ricart"})
    _, op = memory_cache.get()
    assert op == "Ricart"
    # set_state emite `memory.updated` → el sink marca sucio → el próximo get() recompone.
    memapi.set_state({"operator_name": "Leo"})
    _, op2 = memory_cache.get()
    assert op2 == "Leo"


def test_empty_memory_no_crash(fresh_db):
    block, op = memory_cache.get()
    # V2-027: sin perfil, la MISIÓN (identidad, sembrada desde langs) SIEMPRE está — el bloque nunca es vacío,
    # pero el operator_name sí (aún no lo conocemos).
    assert op == "" and "QUIÉN ERES" in block


def test_explicit_refresh_publishes_correction_for_next_turn(fresh_db):
    memapi.set_state({"location": "Valencia"})
    asyncio.run(memory_cache.refresh())
    memapi.set_state({"location": "Castellón"})
    asyncio.run(memory_cache.refresh())
    block, _ = memory_cache.get()
    assert "Castellón" in block
    assert "Ubicación: Valencia" not in block
