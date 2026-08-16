"""Tests de memory/embeddings.py (V2-002 · T46) — dimensión + señal de similitud en castellano."""
import math
import time

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


# ── V2-103: re-intento del backend degradado (2026-08-16) ──────────────────────────────────────────────────
# Un hipo TRANSITORIO de Ollama al arrancar el proceso resolvía `_backend` a 'fastembed'/'hash' y lo dejaba
# cacheado ahí para SIEMPRE — aunque Ollama se recuperase segundos después. Auditoría en vivo: dos hechos
# idénticos duplicados porque el dedup semántico (solo calibrado para 'ollama') quedó apagado toda la sesión.

def test_auto_degraded_backend_rechecks_after_ttl(monkeypatch):
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto", "embed_model": ""})
    monkeypatch.setattr(emb, "_BACKEND_RECHECK_S", 60.0)   # constante leída una vez al importar → parchea el valor
    emb.reset()

    calls = {"ollama": 0}

    def flaky_ollama(texts):
        calls["ollama"] += 1
        return None if calls["ollama"] == 1 else [[0.1] * 768 for _ in texts]

    monkeypatch.setattr(emb, "_ollama_embed", flaky_ollama)
    monkeypatch.setattr(emb, "_fastembed_embed", lambda texts: None)

    assert emb.active_backend() == "hash"          # 1er ping falla → degrada a hash
    t0 = time.time()
    monkeypatch.setattr(time, "time", lambda: t0)
    emb._resolve_backend()
    assert emb.active_backend() == "hash"           # dentro del TTL → no re-sondea

    monkeypatch.setattr(time, "time", lambda: t0 + 61)
    assert emb.active_backend() == "ollama"         # TTL vencido + Ollama ya sano → se recupera solo


def test_forced_backend_never_rechecks(monkeypatch):
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {})   # aísla del store real → manda el env var, no `config/v2.json`
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    emb.reset()
    assert emb.active_backend() == "hash"
    calls = {"n": 0}

    def would_succeed(texts):
        calls["n"] += 1
        return [[0.1] * 768 for _ in texts]

    monkeypatch.setattr(emb, "_ollama_embed", would_succeed)
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 10_000)
    assert emb.active_backend() == "hash"           # forzado por env → nunca se re-sondea
    assert calls["n"] == 0


# V2-031 (2026-08-17, cazado en validación con coste real): `config/v2.json` trae `embed_provider="auto"` de
# fábrica — un string NO VACÍO — así que el `or` de precedencia lo tomaba como valor de config y NUNCA llegaba
# a mirar `ZAELAR_EMBED_BACKEND`, aunque el comentario dijera "store > env > autodetección". El operador pidió
# forzar `fastembed` para evitar Ollama en una tanda de pruebas y, con Ollama disponible, el env var era aire.
def test_env_var_wins_when_config_says_auto_explicitly(monkeypatch):
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto", "embed_model": ""})
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    emb.reset()
    assert emb.active_backend() == "hash"  # antes del fix: "ollama"/autodetección, el env var se ignoraba


def test_healthy_ollama_backend_does_not_repoll(monkeypatch):
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto", "embed_model": ""})
    emb.reset()
    calls = {"n": 0}

    def ok_ollama(texts):
        calls["n"] += 1
        return [[0.1] * 768 for _ in texts]

    monkeypatch.setattr(emb, "_ollama_embed", ok_ollama)
    assert emb.active_backend() == "ollama"
    n_after_first = calls["n"]
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 10_000)
    assert emb.active_backend() == "ollama"         # ya sano → no vuelve a pinguear
    assert calls["n"] == n_after_first


@pytest.mark.skipif(emb.active_backend() != "ollama", reason="requiere Ollama con embeddinggemma")
def test_ollama_spanish_semantics():
    """Con embeddinggemma real: sinónimos/paráfrasis en castellano más cerca que un tema no relacionado."""
    emb.reset()
    q = emb.embed("¿dónde vive el usuario?")
    near = emb.embed("el operador reside en Barcelona")
    far = emb.embed("la receta lleva harina y huevos")
    assert len(q) == 768
    assert _cos(q, near) > _cos(q, far)
