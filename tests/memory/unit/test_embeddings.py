"""Tests de memory/embeddings.py (V2-002 · T46) — dimensión + señal de similitud en castellano."""
import math

import pytest

from memory import embeddings as emb
from memory.schema import EMBED_DIM


def _cos(a, b):
    # los vectores ya vienen L2-normalizados → coseno = producto punto
    return sum(x * y for x, y in zip(a, b))


@pytest.fixture(autouse=True)
def _reset():
    emb.reset()
    yield
    emb.reset()


def test_dimension_is_768(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    emb.reset()
    v = emb.embed("hola, me llamo Ricart y vivo en Barcelona")
    assert len(v) == EMBED_DIM == 768


def test_vectors_are_l2_normalized(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    emb.reset()
    v = emb.embed("una frase cualquiera con varias palabras")
    assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, abs_tol=1e-5)


def test_batch_matches_single(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    emb.reset()
    a = emb.embed("gato")
    b = emb.embed_batch(["gato"])[0]
    assert a == b


def test_hash_backend_lexical_signal(monkeypatch):
    """Aun el fallback determinista da señal léxica: textos que comparten palabras ⇒ más similares."""
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    emb.reset()
    q = emb.embed("el operador se llama Ricart")
    near = emb.embed("el operador Ricart trabaja en castellano")
    far = emb.embed("zumo naranja bicicleta montaña")
    assert _cos(q, near) > _cos(q, far)


def test_empty_batch():
    assert emb.embed_batch([]) == []


@pytest.mark.skipif(emb.active_backend() != "ollama", reason="requiere Ollama con embeddinggemma")
def test_ollama_spanish_semantics():
    """Con embeddinggemma real: sinónimos/paráfrasis en castellano más cerca que un tema no relacionado."""
    emb.reset()
    q = emb.embed("¿dónde vive el usuario?")
    near = emb.embed("el operador reside en Barcelona")
    far = emb.embed("la receta lleva harina y huevos")
    assert len(q) == 768
    assert _cos(q, near) > _cos(q, far)
