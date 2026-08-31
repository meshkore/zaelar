"""Tests for nucleo/flash/memory_cache.py (V2-011 · T114) — the memory block is cached OUTSIDE the turn.

Invariants: (a) `get()` composes the STATE block from `memory.state()` and caches it; (b) it NEVER triggers the
retriever (`memory.query`) — that is on-demand and outside the loop (T115/T116); (c) it is invalidated by `memory.updated`.
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
    # V2-027: the block is the composed STATE (WHO YOU ARE mission + situational) from memory.compose_state.
    assert "Ricart" in block and "directo" in block and "QUIÉN ERES" in block


def test_get_never_fires_the_retriever(fresh_db, monkeypatch):
    """The cached block comes ONLY from state(); touching memory.query() would bring the retriever into the turn."""
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
    # set_state emits `memory.updated` → the sink marks it dirty → the next get() recomposes it.
    memapi.set_state({"operator_name": "Leo"})
    _, op2 = memory_cache.get()
    assert op2 == "Leo"


def test_empty_memory_no_crash(fresh_db):
    block, op = memory_cache.get()
    # V2-027: without a profile, the MISSION (identity, seeded from langs) is ALWAYS present — the block is never empty,
    # but operator_name is (we do not know it yet).
    assert op == "" and "QUIÉN ERES" in block


def test_explicit_refresh_publishes_correction_for_next_turn(fresh_db):
    memapi.set_state({"location": "Valencia"})
    asyncio.run(memory_cache.refresh())
    memapi.set_state({"location": "Castellón"})
    asyncio.run(memory_cache.refresh())
    block, _ = memory_cache.get()
    assert "Castellón" in block
    assert "Ubicación: Valencia" not in block
