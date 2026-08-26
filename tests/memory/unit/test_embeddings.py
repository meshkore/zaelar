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

    def flaky_ollama(texts, *, timeout=None):   # `timeout` lo pasa la sonda (V2-349)
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

    def ok_ollama(texts, *, timeout=None):     # `timeout` lo pasa la sonda (V2-349)
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

    def _ok(texts, *, timeout=None):            # `timeout` lo pasa la sonda (V2-349)
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
    monkeypatch.setattr(emb, "_ollama_embed", lambda texts, *, timeout=None: None)  # never reports an outcome
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


# ── El reloj de la SONDA no es el reloj de una llamada REAL (V2-349, 2026-08-26) ──────────────────────────────
#
# Medido sobre el plató: el PRIMER acceso a memoria de un proceso fresco costaba **20,8 s**. No es el retriever
# —la consulta tarda 25 ms sobre una BD vacía— sino que el DDL de la tabla vectorial necesita `dim()`, eso
# resuelve el backend, y la sonda usaba el presupuesto de una llamada real (`ZAELAR_EMBED_TIMEOUT`, 20 s) contra
# un Ollama vivo pero con la GPU ocupada por el CORAZÓN. El arnés lo estaba midiendo como «la memoria tarda 10 s
# en no encontrar nada».
#
# Lo que hace SEGURO acortarlo es la otra mitad: con 20 s una petición encolada podía llegar a tiempo; con 1,5 s
# no llegaría, y el camino de antes lo habría leído como AUSENCIA → fastembed → 384 rellenados a 768 contra un
# índice sellado embeddinggemma:768. Abaratar la sonda a secas habría comprado 19 s a cambio de cambiar el
# espacio vectorial más a menudo, que es el fallo que a V2-103 le costó una auditoría encontrar.

def _timeout_error():
    import socket
    return socket.timeout("timed out")


def _presupuesto_visto(monkeypatch) -> list:
    """Anota el `timeout` con el que se llama de verdad a la red, que es lo único que importa aquí."""
    vistos: list = []

    def _urlopen(req, timeout=None):
        vistos.append(timeout)
        raise _timeout_error()

    monkeypatch.setattr(emb.urllib.request, "urlopen", _urlopen)
    return vistos


def test_la_SONDA_usa_su_presupuesto_corto_y_no_el_de_una_llamada_real(monkeypatch):
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.delenv("ZAELAR_EMBED_PROBE_TIMEOUT", raising=False)
    monkeypatch.setenv("ZAELAR_EMBED_TIMEOUT", "20")
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto"})
    vistos = _presupuesto_visto(monkeypatch)
    emb.reset()

    emb.active_backend()

    assert vistos, "la sonda no llegó a salir a la red"
    assert vistos[0] == emb.probe_budget_s() < 20.0, (
        f"la sonda volvió a esperar como una llamada real ({vistos[0]}s): son 20 s en el primer acceso a memoria")


def test_una_llamada_REAL_conserva_su_presupuesto_entero(monkeypatch):
    """La contrapartida. Acortarlo TODO sería más fácil y sería otro fallo: en un embed de verdad esperar es
    mejor que degradar el espacio, y esa es una decisión distinta de «¿estás ahí?»."""
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setenv("ZAELAR_EMBED_TIMEOUT", "20")
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto"})
    emb.reset()
    emb._backend, emb._forced = "ollama", True          # backend ya resuelto: esto no es una sonda
    emb._ollama_timeout = False

    vistos: list = []

    def _urlopen(req, timeout=None):
        vistos.append(timeout)
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(emb.urllib.request, "urlopen", _urlopen)
    emb._ollama_embed(["texto de verdad"])

    assert vistos == [20.0], f"una llamada real dejó de esperar lo que le toca: {vistos}"


def test_un_TIMEOUT_de_la_sonda_NO_degrada_el_espacio_vectorial(monkeypatch):
    """El corazón del cambio. Un reloj agotado significa «no lo sé todavía», no «Ollama no está»."""
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto"})
    _presupuesto_visto(monkeypatch)
    monkeypatch.setattr(emb, "_fastembed_embed", lambda texts: [[0.1] * 384 for _ in texts])
    emb.reset()

    assert emb.active_backend() == "ollama", (
        "una sonda que se quedó sin tiempo degradó el proceso entero: 384 rellenados a 768 contra un índice "
        "sellado embeddinggemma — exactamente lo que abaratar la sonda a secas habría comprado")
    assert emb.dim() == 768
    assert emb._resolved_at == 0.0, "y tiene que re-sondear en la próxima llamada, no dentro de 5 minutos"


def test_un_Ollama_AUSENTE_sigue_degradando(monkeypatch):
    """El contrapeso, y la razón de que esto no sea «no degradar nunca»: un servidor que no está no va a
    contestar, y esperarle dejaría la memoria sin recall semántico. La diferencia es que la ausencia se sabe en
    MILISEGUNDOS (conexión rechazada) y el «no lo sé» tarda lo que dure el reloj."""
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto"})
    monkeypatch.setattr(emb.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError("refused")))
    monkeypatch.setattr(emb, "_fastembed_embed", lambda texts: [[0.1] * 384 for _ in texts])
    emb.reset()
    assert emb.active_backend() == "fastembed"


def test_mientras_Ollama_no_conteste_tambien_las_llamadas_reales_usan_el_reloj_corto(monkeypatch):
    """Sin esto, conservar el espacio se paga con un turno muerto: cada embed real esperaría 20 s contra un
    Ollama que ya sabemos que no responde — justo la latencia que midió V2-311. El espacio se conserva igual;
    lo que se difiere es el vector de ESA llamada, como en la rama de saturación."""
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setenv("ZAELAR_EMBED_TIMEOUT", "20")
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto"})
    vistos = _presupuesto_visto(monkeypatch)
    emb.reset()
    emb.active_backend()                                  # la sonda se queda sin tiempo → _ollama_timeout
    vistos.clear()

    emb._ollama_embed(["un embed de verdad"])
    assert vistos == [emb.probe_budget_s()], (
        f"con Ollama mudo, una llamada real volvió a esperar 20 s: {vistos}")

    # …y en cuanto conteste, vuelve el presupuesto entero.
    def _urlopen_ok(req, timeout=None):
        vistos.append(timeout)
        import io
        return io.BytesIO(b'{"embeddings": [[0.5]]}')

    monkeypatch.setattr(emb.urllib.request, "urlopen",
                        lambda req, timeout=None: __import__("contextlib").closing(_urlopen_ok(req, timeout)))
    vistos.clear()
    emb._ollama_embed(["ya contesta"])
    monkeypatch.setattr(emb.urllib.request, "urlopen", lambda req, timeout=None: (_ for _ in ()).throw(
        ConnectionRefusedError("refused")) if vistos.append(timeout) is None else None)
    vistos.clear()
    emb._ollama_embed(["otra más"])
    assert vistos == [20.0], f"tras una respuesta buena el presupuesto entero no volvió: {vistos}"
