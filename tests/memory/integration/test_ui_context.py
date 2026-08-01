"""ESTADO — contexto de UI vivo (widgets abiertos + tareas en marcha).

El ESTADO es la parte VARIABLE del contexto que viaja SIEMPRE en el prompt del cerebro y se ve en el mapa de la
memoria. Aquí se cubren los cuatro eslabones de "lo que el operador tiene delante": (1) el esquema del estado,
(2) el reporte del canvas → estado, (3) la composición del bloque de memoria del FlashBrain, (4) el desempate de
`identify` por el widget abierto.
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


# ── 1. esquema del ESTADO ────────────────────────────────────────────────────────────────────────────────
def test_state_exposes_ui_context_fields(fresh_db):
    st = memapi.state()
    assert st["open_widgets"] == [] and st["activity"] == []      # presentes por defecto


def test_set_state_ui_context_no_clobber(fresh_db):
    memapi.set_state({"operator_name": "Ricart"})
    memapi.set_state({"open_widgets": ["mensajeria", "agenda"]})   # patch superficial: no pisa el nombre
    st = memapi.state()
    assert st["operator_name"] == "Ricart"
    assert st["open_widgets"] == ["mensajeria", "agenda"]


# ── 2. reporte del canvas → ESTADO (endpoint) ────────────────────────────────────────────────────────────
def test_canvas_state_endpoint_normalizes_and_writes(fresh_db):
    seen = []
    sink = lambda rec: seen.append(rec["topic"]) if rec["topic"] == "memory.updated" else None
    bus.add_sink(sink)
    try:
        from server.voice_api import canvas_state
        # ids de instancia del navegador (navegador::t3) → base; duplicados colapsados; orden preservado
        out = asyncio.run(canvas_state({"open": ["mensajeria", "navegador::t3", "navegador::t7", "mensajeria"]}))
        assert out.status_code == 200
        assert memapi.state()["open_widgets"] == ["mensajeria", "navegador"]
        assert "memory.updated" in seen                            # el mapa/prompt se enteran en vivo
    finally:
        bus.remove_sink(sink)


# ── 3. composición del bloque de memoria del FlashBrain ──────────────────────────────────────────────────
def test_compose_block_lists_open_widgets_and_activity(fresh_db):
    from nucleo.flash import memory_cache
    memory_cache.reset()
    memapi.set_state({"open_widgets": ["mensajeria"], "activity": ["Modificando el widget «agenda»…"]})
    block, _op = memory_cache._compose()
    assert "Widgets ABIERTOS" in block and "mensajeria" in block
    assert "Tareas en marcha" in block and "agenda" in block


# ── 4. desempate de identify por el widget ABIERTO ───────────────────────────────────────────────────────
def test_identify_prefers_open_widget_on_tie(monkeypatch):
    from widgets import runtime
    # dos widgets que EMPATAN para la misma query (mismo score por título)
    rows = [
        {"w": {"id": "agenda", "title": "agenda"}, "kws": ["agenda"], "kw_tokens": {"agenda"},
         "name": "agenda", "title": "agenda", "name_tokens": {"agenda"}, "desc_tokens": set()},
        {"w": {"id": "agenda-pro", "title": "agenda"}, "kws": ["agenda"], "kw_tokens": {"agenda"},
         "name": "agenda-pro", "title": "agenda", "name_tokens": {"agenda", "pro"}, "desc_tokens": set()},
    ]
    monkeypatch.setattr(runtime, "_identify_index", lambda: rows)
    # sin contexto → ambiguo, sin match
    amb = runtime.identify("abre la agenda")
    assert amb["ambiguous"] is True and amb["match"] is None
    # con el widget abierto → desempata a su favor, sin preguntar
    resolved = runtime.identify("abre la agenda", open_ids=["agenda-pro::x", "otro"])
    assert resolved["ambiguous"] is False and resolved["match"] == "agenda-pro"
