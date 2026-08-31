"""Tests for memory/rerank.py (V2-030) — model-agnostic abstraction, FAIL-OPEN, does not touch STATE/SHORT.

The reranker is an optional IMPROVEMENT to long-context recall: if it fails, the system must continue returning the
retriever's order unchanged (never crash or block). And with provider 'off' (default), it must be a complete no-op.
"""
import pytest

from memory import rerank


@pytest.fixture(autouse=True)
def _off_by_default(monkeypatch):
    # Isolate from the repo config: without env, the provider is 'off'.
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
    assert rerank.rerank("¿qué deporte me gusta?", c) is c   # same object, untouched


def test_unknown_provider_is_noop(monkeypatch):
    monkeypatch.setattr(rerank, "_cfg", lambda: {"rerank_provider": "cohere"})  # unimplemented → orderer None
    c = _cands()
    out = rerank.rerank("x", c)
    assert [m["id"] for m in out] == [1, 2, 3]                # order unchanged


def test_failopen_when_orderer_raises(monkeypatch):
    monkeypatch.setattr(rerank, "_cfg", lambda: {"rerank_provider": "openai"})

    def _boom(query, texts):
        raise RuntimeError("api down")

    # `_ORDERERS` maps provider -> function NAME since 2026-08-19 (see the table's comment in
    # memory/rerank.py): patch the FUNCTION, which is also what a reader would expect to patch.
    monkeypatch.setattr(rerank, "_order_openai", _boom)
    c = _cands()
    out = rerank.rerank("x", c)
    assert [m["id"] for m in out] == [1, 2, 3]                # fail-open: input order


def test_reorders_and_blends(monkeypatch):
    monkeypatch.setattr(rerank, "_cfg", lambda: {"rerank_provider": "openai", "rerank_blend": 0.85})
    # Deterministic orderer: puts index 0 ('padel') last and 2 ('perro') first.
    monkeypatch.setattr(rerank, "_order_openai", lambda q, texts: [2, 1, 0])
    out = rerank.rerank("x", _cands())
    assert [m["id"] for m in out] == [3, 2, 1]                # new permutation applied
    assert out[0]["rr"] == 1.0 and out[0]["via"] == "rerank"  # marked
    assert out[-1]["rr"] < out[0]["rr"]                       # decreasing rerank score


def test_empty_candidates_safe():
    assert rerank.rerank("x", []) == []


def test_status_shape():
    s = rerank.status()
    assert set(s) >= {"provider", "enabled", "available", "top_n"}
    assert s["provider"] == "off" and s["enabled"] is False
