"""nucleo/flash/probe.py::run_turn — semantic recall must not search by the COMPLETE turn text when it
carried a prepended [SYSTEM] note (2026-08-17, live audit against memory/_data/zaelar.db).

Real case: a Telegram note about trading ("Near our tp1 we take out 20-30%...") was prepended to
"QUE SABES DE MI ? PERSONA, FAMILIA, COSAS, PROPIEDADES" before building the recall query — the trading noise
dominated the semantic vector and buried the family/car facts that DID exist in the long-term memory. The
model responded without data in front of it and hallucinated a family member that no pill mentions. The same
fix is mirrored in `voice/engine/llm/providers/nucleo.py` (the real voice provider); this test covers the test
channel path (`probe.py`), which can be invoked without a LiveKit session.

2026-08-23 (F1): the query no longer travels as `recall_query=` to `build_flash_system` —that was the
TEST COMPATIBILITY path, which composes recall INLINE and, with slow memory, blocked the entire process—
but instead to `nucleo/turn/recall_budget.compose()`, outside the event loop and bounded. The invariant is the
same and is monitored at the new seam: what is SEARCHED FOR is the operator's wording, never the prepended note.
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
    """Sentinel: stops the turn just before calling the real model (this test does not need a network)."""


class _NoNetworkFastClient:
    async def stream(self, *_a, **_kw):
        raise _StreamStop("test: sin red, corte deliberado antes del modelo")
        yield  # pragma: no cover — never reached; makes this a valid async generator


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
    brain_notes.drain()  # clears any remnants from another test (global mailbox)
    yield sid
    probe._SESSIONS.pop(sid, None)
    brain_notes.drain()


def test_recall_query_excludes_prepended_system_note(fresh_db, probe_session, monkeypatch):
    memapi.write_now("Tiene dos hijos de 9 y 11 años.", kind="fact", level="long")

    captured: dict = {}
    _orig_build = prompt_mod.build_flash_system

    def _spy_build(**kwargs):
        captured["turn_text"] = kwargs.get("turn_text", "")
        # `recall_query` must remain EMPTY: using it means composing inside the loop again.
        captured["recall_query_legacy"] = kwargs.get("recall_query", "")
        return _orig_build(**kwargs)

    # The query is monitored WHERE IT NOW TRAVELS: the budgeted guard. Spying on `build_flash_system` would still
    # pass with the contamination reintroduced, because only the composed block reaches it there.
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
    assert res["ok"] is False  # the turn is deliberately cut off before calling the model (no network in the test)

    # The recall QUERY is ONLY the operator's question — the Telegram note does not travel in it.
    assert "QUE SABES DE MI" in captured["recall_query"]
    assert "Telegram" not in captured["recall_query"]
    assert "tp1" not in captured["recall_query"]
    # The COMPLETE TURN (what the model sees) still carries the note — no information was lost; it was only
    # removed from the search vector.
    assert "Telegram" in captured["turn_text"]
    # And the compatibility path remains EMPTY: using it means composing recall inside the event loop, which is
    # what brought down the entire engine on 2026-08-23 with slow memory.
    assert captured["recall_query_legacy"] == ""

    # With the clean query, the real fact IS recovered (previously it was buried under the trading noise).
    system, ids = prompt_mod.build_flash_system(recall_query=captured["recall_query"])
    assert "hijos" in system
    assert ids
