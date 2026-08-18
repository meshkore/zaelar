"""Tests de memory/rerank.py (V2-030) — abstracción model-agnostic, FAIL-OPEN, no toca ESTADO/CORTO.

El reranker es una MEJORA opcional del recall largo: si falla, el sistema debe seguir devolviendo el orden del
retriever intacto (nunca romper ni bloquear). Y con proveedor 'off' (default) debe ser un no-op total.
"""
import pytest

from memory import rerank


@pytest.fixture(autouse=True)
def _off_by_default(monkeypatch):
    # aislar de la config del repo: sin env, el proveedor es 'off'.
    monkeypatch.delenv("MEMORY_RERANK", raising=False)
    monkeypatch.setattr(rerank, "_cfg", lambda: {"rerank_provider": "off"})
    yield


def _cands():
    return [
        {"id": 1, "text": "me gusta el padel", "score": 0.3},
        {"id": 2, "text": "vivo en barcelona", "score": 0.9},
        {"id": 3, "text": "tengo un perro", "score": 0.5},
    ]


def test_off_is_noop():
    assert not rerank.enabled()
    c = _cands()
    assert rerank.rerank("¿qué deporte me gusta?", c) is c   # mismo objeto, sin tocar


def test_unknown_provider_is_noop(monkeypatch):
    monkeypatch.setattr(rerank, "_cfg", lambda: {"rerank_provider": "cohere"})  # sin implementar → orderer None
    c = _cands()
    out = rerank.rerank("x", c)
    assert [m["id"] for m in out] == [1, 2, 3]                # orden intacto


def test_failopen_when_orderer_raises(monkeypatch):
    monkeypatch.setattr(rerank, "_cfg", lambda: {"rerank_provider": "openai"})

    def _boom(query, texts):
        raise RuntimeError("api down")

    # `_ORDERERS` maps provider -> function NAME since 2026-08-19 (see the table's comment in
    # memory/rerank.py): patch the FUNCTION, which is also what a reader would expect to patch.
    monkeypatch.setattr(rerank, "_order_openai", _boom)
    c = _cands()
    out = rerank.rerank("x", c)
    assert [m["id"] for m in out] == [1, 2, 3]                # fail-open: orden de entrada


def test_reorders_and_blends(monkeypatch):
    monkeypatch.setattr(rerank, "_cfg", lambda: {"rerank_provider": "openai", "rerank_blend": 0.85})
    # orderer determinista: pone el índice 0 ('padel') el último y el 2 ('perro') el primero.
    monkeypatch.setattr(rerank, "_order_openai", lambda q, texts: [2, 1, 0])
    out = rerank.rerank("x", _cands())
    assert [m["id"] for m in out] == [3, 2, 1]                # nueva permutación aplicada
    assert out[0]["rr"] == 1.0 and out[0]["via"] == "rerank"  # marcado
    assert out[-1]["rr"] < out[0]["rr"]                       # score de rerank decreciente


def test_empty_candidates_safe():
    assert rerank.rerank("x", []) == []


def test_status_shape():
    s = rerank.status()
    assert set(s) >= {"provider", "enabled", "available", "top_n"}
    assert s["provider"] == "off" and s["enabled"] is False
