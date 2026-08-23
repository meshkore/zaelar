"""Tests de memory/embeddings.py (V2-002 · T46) — dimensión + señal de similitud en castellano."""
import math
import time
from unittest import mock

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


# ── BUSY IS NOT ABSENT (2026-08-19) ─────────────────────────────────────────────────────────────────────────
# Reproduced live: `/api/embed` answering `{"error":"server busy, please try again.  maximum pending requests
# exceeded"}` while `/api/tags` served fine and `embeddinggemma:latest` was pulled. The probe read that as "Ollama
# is gone" and demoted the whole process to fastembed for 300s — and demoting is not a milder version of the same
# thing, it CHANGES THE VECTOR SPACE (fastembed 384 padded to 768 against an index stamped embeddinggemma:768), so
# the writer refuses to store vectors and the reader drops its vector channels. This is the root cause behind both
# of those guards and behind the 51.6% vector-less rows the V2-103 audit found.
def _busy_error():
    import urllib.error, io
    return urllib.error.HTTPError(
        "http://x/api/embed", 503, "Service Unavailable", {},
        io.BytesIO(b'{"error":"server busy, please try again.  maximum pending requests exceeded"}'))


def test_a_saturated_ollama_keeps_the_vector_space_instead_of_demoting(monkeypatch):
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto"})
    monkeypatch.setattr(emb.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(_busy_error()))
    monkeypatch.setattr(emb, "_fastembed_embed", lambda texts: [[0.1] * 384 for _ in texts])
    emb.reset()

    assert emb.active_backend() == "ollama", "un Ollama SATURADO no es un Ollama ausente"
    assert emb.dim() == 768, "el espacio declarado tiene que seguir siendo el del índice"
    emb.embed("una consulta")
    assert emb.last_degraded is True, (
        "el vector concreto sí falla y hay que DECIRLO: es lo que manda la lectura a léxico y difiere el vector "
        "del write a la reparación de REM"
    )


def test_a_saturated_ollama_re_probes_on_the_very_next_call(monkeypatch):
    """A drained queue can happen a second later, so the 300s TTL is the wrong clock for this case."""
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto"})
    monkeypatch.setattr(emb.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(_busy_error()))
    emb.reset()
    emb.active_backend()
    assert emb._resolved_at == 0.0, "con el TTL normal la recuperación llegaría hasta 5 minutos tarde"

    calls = {"n": 0}

    def _ok(texts):
        calls["n"] += 1
        return [[0.2] * 768 for _ in texts]

    monkeypatch.setattr(emb, "_ollama_embed", _ok)
    emb.embed("otra consulta")
    assert calls["n"] >= 1 and emb.last_degraded is False, "al drenarse la cola debe recuperarse en el acto"


def test_an_ABSENT_ollama_still_demotes(monkeypatch):
    """The counterweight, and the reason this is not just "never demote": a server that is not there will not
    drain, so waiting for it would leave the memory with no semantic recall at all. Without this test the fix is
    indistinguishable from disabling the fallback."""
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto"})
    monkeypatch.setattr(emb.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError("refused")))
    monkeypatch.setattr(emb, "_fastembed_embed", lambda texts: [[0.1] * 384 for _ in texts])
    emb.reset()
    assert emb.active_backend() == "fastembed"


def test_busy_classification_is_about_saturation_only():
    assert emb._looks_busy("server busy, please try again.  maximum pending requests exceeded")
    assert emb._looks_busy("Ollama is overloaded")
    assert not emb._looks_busy("connection refused")
    assert not emb._looks_busy('model "embeddinggemma" not found')
    assert not emb._looks_busy(None)


def test_the_busy_flag_never_leaks_from_a_previous_probe(monkeypatch):
    """Regression for an ORDER-DEPENDENT bug this fix introduced and a pre-existing test caught: `_ollama_busy` is
    module state, so a probe that never reaches `_ollama_embed` (mocked out, or short-circuited) would inherit
    someone else's verdict and keep a dead Ollama selected forever. The kind of defect that passes in one test
    order and fails in another, which is why it is pinned rather than just fixed."""
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto"})
    emb._ollama_busy = True                                   # stale verdict from an earlier call
    monkeypatch.setattr(emb, "_ollama_embed", lambda texts: None)   # never reports an outcome
    monkeypatch.setattr(emb, "_fastembed_embed", lambda texts: [[0.1] * 384 for _ in texts])
    emb.reset()
    assert emb.active_backend() == "fastembed", "decidió con el veredicto de otra llamada"
    assert emb._ollama_busy is False


# ── el degradado se VE, no solo se loguea (auditoría de arquitectura 2026-08-23, H7) ──────────────────────────
@pytest.mark.parametrize("backend, forzado, hay_ambar, por_que", [
    ("hash",      False, True,  "Ollama caído: el recall por significado queda APAGADO y nada lo decía"),
    ("fastembed", False, True,  "degradado a escala (T176), misma clase de pérdida silenciosa"),
    ("hash",      True,  False, "FORZADO por la suite en cada corrida — el ámbar permanente se aprende a ignorar"),
    ("ollama",    False, False, "sano: no hay nada que reportar"),
])
def test_un_backend_degradado_que_nadie_pidio_pone_la_salud_en_ambar(backend, forzado, hay_ambar, por_que):
    """La regla que este módulo tenía a medias: avisaba, pero solo por `logging` de la stdlib — sin marca de
    tiempo y en medio del ruido del arranque. El gemelo es el canal de paráfrasis mudo desde 2026-08-18."""
    with mock.patch("voice.health_state.record") as rec:
        emb._warn_if_degraded(backend, forzado)
        assert rec.called is hay_ambar, por_que


def test_y_un_fallo_de_observabilidad_JAMAS_rompe_la_memoria():
    """Sin esto, añadir un aviso convierte un recall degradado en un recall que revienta — peor que el fallo
    que se quería hacer visible."""
    with mock.patch("voice.health_state.record", side_effect=RuntimeError("bus caído")):
        emb._warn_if_degraded("hash", False)   # no debe lanzar
