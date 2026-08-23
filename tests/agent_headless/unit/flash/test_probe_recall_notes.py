"""nucleo/flash/probe.py::run_turn — el recall semántico no debe buscar por el texto COMPLETO del turno cuando
llevaba una nota [SISTEMA] antepuesta (2026-08-17, auditoría en vivo contra memory/_data/zaelar.db).

Caso real: una nota de Telegram sobre trading ("Near our tp1 we take out 20-30%...") se anteponía a
"QUE SABES DE MI ? PERSONA, FAMILIA, COSAS, PROPIEDADES" antes de construir la query de recall — el ruido de
trading dominaba el vector semántico y enterraba los hechos de familia/coche que SÍ existían en el largo
plazo. El modelo respondió sin datos delante y alucinó un familiar que ninguna píldora menciona. Mismo fix
espejado en `voice/engine/llm/providers/nucleo.py` (el proveedor de voz real); este test cubre la ruta del
canal de prueba (`probe.py`), que es la que se puede invocar sin sesión LiveKit.

2026-08-23 (F1): la query ya no viaja como `recall_query=` a `build_flash_system` —esa era la ruta de
COMPATIBILIDAD PARA TESTS, que compone el recall EN LÍNEA y con la memoria lenta bloqueaba el proceso entero—
sino a `nucleo/turn/recall_budget.compose()`, fuera del event loop y acotada. El invariante es el mismo y se
vigila en la costura nueva: lo que se BUSCA son las palabras del operador, nunca la nota antepuesta.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from nucleo.flash import probe
from nucleo.flash import prompt as prompt_mod
from voice import brain_notes


class _StreamStop(Exception):
    """Sentinel: para el turno justo antes de llamar al modelo real (no hace falta red en este test)."""


class _NoNetworkFastClient:
    async def stream(self, *_a, **_kw):
        raise _StreamStop("test: sin red, corte deliberado antes del modelo")
        yield  # pragma: no cover — nunca se alcanza; hace de esto un generador async válido


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


@pytest.fixture
def probe_session():
    sid = "test-recall-notes"
    brain_notes.drain()  # limpia cualquier resto de otro test (mailbox global)
    yield sid
    probe._SESSIONS.pop(sid, None)
    brain_notes.drain()


def test_recall_query_excludes_prepended_system_note(fresh_db, probe_session, monkeypatch):
    memapi.write_now("Tiene dos hijos de 9 y 11 años.", kind="fact", level="long")

    captured: dict = {}
    _orig_build = prompt_mod.build_flash_system

    def _spy_build(**kwargs):
        captured["turn_text"] = kwargs.get("turn_text", "")
        # `recall_query` tiene que quedar VACÍO: usarlo es volver a componer dentro del loop.
        captured["recall_query_legacy"] = kwargs.get("recall_query", "")
        return _orig_build(**kwargs)

    # La query se vigila DONDE AHORA VIAJA: la guarda con presupuesto. Espiar `build_flash_system` seguiría
    # pasando en verde con la contaminación de vuelta, porque ahí ya solo llega el bloque compuesto.
    from nucleo.turn import recall_budget as _recall
    _orig_compose = _recall.compose

    async def _spy_compose(query, timings=None):
        captured["recall_query"] = query or ""
        return await _orig_compose(query, timings)

    monkeypatch.setattr(_recall, "compose", _spy_compose)
    monkeypatch.setattr(prompt_mod, "build_flash_system", _spy_build)
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _NoNetworkFastClient)

    brain_notes.push("[SISTEMA] Telegram: 1 mensaje(s) nuevo(s) que le importan al operador: ? (grupo GOLD "
                      "SIMPLIFICADO): Near our tp1 we take out 20-30% of this trade and set breakeven ok?. "
                      "Están en el widget 'mensajeria' (di [[show:mensajeria]] para enseñárselo).")

    res = asyncio.run(probe.run_turn("QUE SABES DE MI ? PERSONA, FAMILIA, COSAS, PROPIEDADES",
                                     sid=probe_session, ingest=False))
    assert res["ok"] is False  # el turno se corta a propósito antes de llamar al modelo (sin red en el test)

    # la QUERY de recall es SOLO la pregunta del operador — la nota de Telegram no viaja en ella.
    assert "QUE SABES DE MI" in captured["recall_query"]
    assert "Telegram" not in captured["recall_query"]
    assert "tp1" not in captured["recall_query"]
    # el TURNO completo (lo que ve el modelo) SÍ sigue llevando la nota — no se ha perdido información, solo
    # se ha sacado del vector de búsqueda.
    assert "Telegram" in captured["turn_text"]
    # y la ruta de compatibilidad se queda VACÍA: usarla es componer el recall dentro del event loop, que es
    # lo que tumbó el motor entero el 2026-08-23 con la memoria lenta.
    assert captured["recall_query_legacy"] == ""

    # con la query limpia, el hecho real SÍ se recupera (antes se enterraba bajo el ruido de trading).
    system, ids = prompt_mod.build_flash_system(recall_query=captured["recall_query"])
    assert "hijos" in system
    assert ids
