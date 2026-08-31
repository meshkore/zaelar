"""STATE — live UI context (open widgets + tasks in progress).

STATE is the VARIABLE part of the context that ALWAYS travels in the brain's prompt and is shown on the memory
map. This covers the four links in "what the operator has in front of them": (1) the state schema,
(2) the canvas → state report, (3) the composition of the FlashBrain memory block, (4) breaking an `identify` tie
in favor of the open widget.
"""
import asyncio

import pytest

import bus
from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


# ── 1. STATE schema ────────────────────────────────────────────────────────────────────────────────
def test_state_exposes_ui_context_fields(fresh_db):
    st = memapi.state()
    assert st["open_widgets"] == [] and st["activity"] == []      # present by default


def test_set_state_ui_context_no_clobber(fresh_db):
    memapi.set_state({"operator_name": "Ricart"})
    memapi.set_state({"open_widgets": ["mensajeria", "agenda"]})   # shallow patch: does not overwrite the name
    st = memapi.state()
    assert st["operator_name"] == "Ricart"
    assert st["open_widgets"] == ["mensajeria", "agenda"]


# ── 2. canvas → STATE report (endpoint) ────────────────────────────────────────────────────────────
def test_canvas_state_endpoint_normalizes_and_writes(fresh_db):
    seen = []
    sink = lambda rec: seen.append(rec["topic"]) if rec["topic"] == "memory.updated" else None
    bus.add_sink(sink)
    try:
        from server.voice_api import canvas_state
        # browser instance IDs (navegador::t3) → base; duplicates collapsed; order preserved
        out = asyncio.run(canvas_state({"open": ["mensajeria", "navegador::t3", "navegador::t7", "mensajeria"]}))
        assert out.status_code == 200
        assert memapi.state()["open_widgets"] == ["mensajeria", "navegador"]
        assert "memory.updated" in seen                            # the map/prompt are updated live
    finally:
        bus.remove_sink(sink)


# ── 3. composition of the FlashBrain memory block ──────────────────────────────────────────────────
def test_compose_block_lists_open_widgets_and_activity(fresh_db):
    from nucleo.flash import memory_cache
    memory_cache.reset()
    memapi.set_state({"open_widgets": ["mensajeria"], "activity": ["Modificando el widget «agenda»…"]})
    block, _op = memory_cache._compose()
    assert "Widgets ABIERTOS" in block and "mensajeria" in block
    assert "Tareas en marcha" in block and "agenda" in block


# ── 4. breaking an identify tie in favor of the OPEN widget ───────────────────────────────────────────────────────
def test_identify_prefers_open_widget_on_tie(monkeypatch):
    from widgets import runtime
    # two widgets tied for the same query (same score by title)
    rows = [
        {"w": {"id": "agenda", "title": "agenda"},
         "aliases": ["agenda"], "alias_tokens": {"agenda"}},
        {"w": {"id": "agenda-pro", "title": "agenda"},
         "aliases": ["agenda"], "alias_tokens": {"agenda"}},
    ]
    monkeypatch.setattr(runtime, "_identify_index", lambda: rows)
    # without context → ambiguous, no match
    amb = runtime.identify("abre la agenda")
    assert amb["ambiguous"] is True and amb["match"] is None
    # with the widget open → breaks the tie in its favor, without asking
    resolved = runtime.identify("abre la agenda", open_ids=["agenda-pro::x", "otro"])
    assert resolved["ambiguous"] is False and resolved["match"] == "agenda-pro"
