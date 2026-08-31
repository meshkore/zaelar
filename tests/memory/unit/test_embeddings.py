"""Tests for memory/embeddings.py (V2-002 · T46) — dimension + similarity signal in Spanish."""
import math
import time
from unittest import mock

import pytest

from memory import embeddings as emb
from memory.schema import EMBED_DIM


def _cos(a, b):
    # the vectors are already L2-normalized → cosine = dot product
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
    """Even the deterministic fallback provides a lexical signal: texts that share words are more similar."""
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    emb.reset()
    q = emb.embed("el operador se llama Ricart")
    near = emb.embed("el operador Ricart trabaja en castellano")
    far = emb.embed("zumo naranja bicicleta montaña")
    assert _cos(q, near) > _cos(q, far)


def test_empty_batch():
    assert emb.embed_batch([]) == []


# ── V2-103: retrying the degraded backend (2026-08-16) ──────────────────────────────────────────────────
# A TRANSIENT hiccup from Ollama when starting the process resolved `_backend` to 'fastembed'/'hash' and left it
# cached there FOREVER — even if Ollama recovered seconds later. Live audit: two identical facts were duplicated
# because semantic deduplication (calibrated only for 'ollama') remained disabled for the entire session.

def test_auto_degraded_backend_rechecks_after_ttl(monkeypatch):
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto", "embed_model": ""})
    monkeypatch.setattr(emb, "_BACKEND_RECHECK_S", 60.0)   # constant read once at import → patch the value
    emb.reset()

    calls = {"ollama": 0}

    def flaky_ollama(texts, *, timeout=None):   # `timeout` is passed by the probe (V2-349)
        calls["ollama"] += 1
        return None if calls["ollama"] == 1 else [[0.1] * 768 for _ in texts]

    monkeypatch.setattr(emb, "_ollama_embed", flaky_ollama)
    monkeypatch.setattr(emb, "_fastembed_embed", lambda texts: None)

    assert emb.active_backend() == "hash"          # 1er ping falla → degrada a hash
    t0 = time.time()
    monkeypatch.setattr(time, "time", lambda: t0)
    emb._resolve_backend()
    assert emb.active_backend() == "hash"           # within the TTL → no new probe

    monkeypatch.setattr(time, "time", lambda: t0 + 61)
    assert emb.active_backend() == "ollama"         # TTL expired + Ollama healthy again → recovers automatically


def test_forced_backend_never_rechecks(monkeypatch):
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {})   # isolate from the real store → env var wins, not `config/v2.json`
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
    assert emb.active_backend() == "hash"           # forced by env → never probed again
    assert calls["n"] == 0


# V2-031 (2026-08-17, caught during validation at real cost): `config/v2.json` ships with `embed_provider="auto"`
# by default — a NON-EMPTY string — so the precedence `or` took it as the config value and NEVER reached
# `ZAELAR_EMBED_BACKEND`, even though the comment said "store > env > autodetection". The operator asked to force
# `fastembed` to avoid Ollama in a test run and, with Ollama available, the env var had no effect.
def test_env_var_wins_when_config_says_auto_explicitly(monkeypatch):
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto", "embed_model": ""})
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    emb.reset()
    assert emb.active_backend() == "hash"  # before the fix: "ollama"/autodetection, the env var was ignored


def test_healthy_ollama_backend_does_not_repoll(monkeypatch):
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto", "embed_model": ""})
    emb.reset()
    calls = {"n": 0}

    def ok_ollama(texts, *, timeout=None):     # `timeout` is passed by the probe (V2-349)
        calls["n"] += 1
        return [[0.1] * 768 for _ in texts]

    monkeypatch.setattr(emb, "_ollama_embed", ok_ollama)
    assert emb.active_backend() == "ollama"
    n_after_first = calls["n"]
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 10_000)
    assert emb.active_backend() == "ollama"         # already healthy → no ping again
    assert calls["n"] == n_after_first


@pytest.mark.skipif(emb.active_backend() != "ollama", reason="requiere Ollama con embeddinggemma")
def test_ollama_spanish_semantics():
    """With real embeddinggemma: synonyms/paraphrases in Spanish are closer than an unrelated topic."""
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

    def _ok(texts, *, timeout=None):            # `timeout` is passed by the probe (V2-349)
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


# ── degradation is VISIBLE, not merely logged (architecture audit 2026-08-23, H7) ──────────────────────────
@pytest.mark.parametrize("backend, forzado, hay_ambar, por_que", [
    ("hash",      False, True,  "Ollama caído: el recall por significado queda APAGADO y nada lo decía"),
    ("fastembed", False, True,  "degradado a escala (T176), misma clase de pérdida silenciosa"),
    ("hash",      True,  False, "FORZADO por la suite en cada corrida — el ámbar permanente se aprende a ignorar"),
    ("ollama",    False, False, "sano: no hay nada que reportar"),
])
def test_un_backend_degradado_que_nadie_pidio_pone_la_salud_en_ambar(backend, forzado, hay_ambar, por_que):
    """The rule this module only partly had: it warned, but only through stdlib `logging` — without a timestamp
    and amid startup noise. Its counterpart is the silent paraphrase channel since 2026-08-18."""
    with mock.patch("voice.health_state.record") as rec:
        emb._warn_if_degraded(backend, forzado)
        assert rec.called is hay_ambar, por_que


def test_y_un_fallo_de_observabilidad_JAMAS_rompe_la_memoria():
    """Without this, adding a warning turns degraded recall into recall that crashes — worse than the failure
    that was meant to be made visible."""
    with mock.patch("voice.health_state.record", side_effect=RuntimeError("bus caído")):
        emb._warn_if_degraded("hash", False)   # must not raise


# ── The PROBE clock is not the clock for a REAL call (V2-349, 2026-08-26) ──────────────────────────────
#
# Measured on the platform: the FIRST memory access of a fresh process took **20.8 s**. It is not the retriever
# —the query takes 25 ms on an empty database— but the vector table DDL needs `dim()`, which resolves the backend,
# and the probe used the budget of a real call (`ZAELAR_EMBED_TIMEOUT`, 20 s) against a live Ollama whose GPU was
# occupied by the CORE. The harness measured this as «memory takes 10 s to find nothing».
#
# What makes shortening it SAFE is the other half: with 20 s a queued request could arrive in time; with 1.5 s it
# would not, and the previous path would have read it as ABSENCE → fastembed → 384 padded to 768 against a sealed
# embeddinggemma:768 index. Merely cheapening the probe would have bought 19 s at the cost of changing the vector
# space more often, which is the failure that cost V2-103 an audit to uncover.

def _timeout_error():
    import socket
    return socket.timeout("timed out")


def _presupuesto_visto(monkeypatch) -> list:
    """Records the `timeout` used to actually call the network, which is the only thing that matters here."""
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
    """The counterpart. Shortening EVERYTHING would be easier and would be another failure: for a real embed,
    waiting is better than degrading the space, and that is a different decision from «are you there?»."""
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setenv("ZAELAR_EMBED_TIMEOUT", "20")
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto"})
    emb.reset()
    emb._backend, emb._forced = "ollama", True          # backend already resolved: this is not a probe
    emb._ollama_timeout = False

    vistos: list = []

    def _urlopen(req, timeout=None):
        vistos.append(timeout)
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(emb.urllib.request, "urlopen", _urlopen)
    emb._ollama_embed(["texto de verdad"])

    assert vistos == [20.0], f"una llamada real dejó de esperar lo que le toca: {vistos}"


def test_un_TIMEOUT_de_la_sonda_NO_degrada_el_espacio_vectorial(monkeypatch):
    """The heart of the change. An exhausted clock means «I don't know yet», not «Ollama is not there».

    V2-350 le puso su precondición EXPLÍCITA: esto vale donde hay un índice sellado que defender. Antes el caso
    no la declaraba y pasaba por el ambiente — verde al correr el fichero solo, rojo en la suite entera, según
    which database happened to be in front of it. A test that depends on this asserts less than it appears to."""
    from memory import reembed
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto"})
    monkeypatch.setattr(reembed, "stored_signature", lambda: "ollama:embeddinggemma:768")
    _presupuesto_visto(monkeypatch)
    monkeypatch.setattr(emb, "_fastembed_embed", lambda texts: [[0.1] * 384 for _ in texts])
    emb.reset()

    assert emb.active_backend() == "ollama", (
        "una sonda que se quedó sin tiempo degradó el proceso entero: 384 rellenados a 768 contra un índice "
        "sellado embeddinggemma — exactamente lo que abaratar la sonda a secas habría comprado")
    assert emb.dim() == 768
    assert emb._resolved_at == 0.0, "y tiene que re-sondear en la próxima llamada, no dentro de 5 minutos"


def test_un_Ollama_AUSENTE_sigue_degradando(monkeypatch):
    """The counterweight, and the reason this is not «never demote»: a server that is not there will not
    respond, and waiting for it would leave memory without semantic recall. The difference is that absence is known
    in MILLISECONDS (connection refused), while «I don't know» takes as long as the clock runs."""
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto"})
    monkeypatch.setattr(emb.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError("refused")))
    monkeypatch.setattr(emb, "_fastembed_embed", lambda texts: [[0.1] * 384 for _ in texts])
    emb.reset()
    assert emb.active_backend() == "fastembed"


def test_mientras_Ollama_no_conteste_tambien_las_llamadas_reales_usan_el_reloj_corto(monkeypatch):
    """Without this, preserving the space costs a dead turn: every real embed would wait 20 s for an Ollama
    that we already know does not respond — exactly the latency measured by V2-311. The space is still preserved;
    what is deferred is the vector for THAT call, as in the saturation branch."""
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setenv("ZAELAR_EMBED_TIMEOUT", "20")
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto"})
    vistos = _presupuesto_visto(monkeypatch)
    emb.reset()
    emb.active_backend()                                  # the probe times out → _ollama_timeout
    vistos.clear()

    emb._ollama_embed(["un embed de verdad"])
    assert vistos == [emb.probe_budget_s()], (
        f"con Ollama mudo, una llamada real volvió a esperar 20 s: {vistos}")

    # …and as soon as it responds, the full budget returns.
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


# ── «A timeout is not an absence» ONLY where there is something to defend (V2-350, 2026-08-27) ────────────────────
#
# V2-349 keeps `ollama` when the probe runs out of time, to avoid looking up embeddinggemma vectors with
# padded fastembed queries. Correct when there is a sealed index; TOO BROAD when there is not.
#
# Measured on the platform (round 13): the workspace DID have 6 pills, 1 vector, and no `.embedsig`, and every recall
# came out «recall on FTS only» — in other words, half-working memory each round because it protected a nonexistent
# space. There fastembed provides REAL semantic recall consistent with itself. The US does have a signature, and
# preserving it there is correct: that is the case V2-103 protects.

def _sin_ollama_a_tiempo(monkeypatch):
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "auto"})
    monkeypatch.setattr(emb.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(_timeout_error()))
    monkeypatch.setattr(emb, "_fastembed_embed", lambda texts: [[0.1] * 384 for _ in texts])


def test_SIN_indice_sellado_un_timeout_SI_degrada(monkeypatch):
    """There is no space to corrupt, and remaining lexical-only is worse than a fastembed consistent with itself."""
    from memory import reembed
    _sin_ollama_a_tiempo(monkeypatch)
    monkeypatch.setattr(reembed, "stored_signature", lambda: None)
    emb.reset()

    assert emb.active_backend() == "fastembed", (
        "se conservó un Ollama que no contesta sobre una BD sin sellar: no protege nada y cuesta el canal "
        "semántico entero — es lo que dejaba al plató en «recall on FTS only» cada ronda")


def test_CON_indice_sellado_un_timeout_NO_degrada(monkeypatch):
    """The other direction, and the one that protects V2-103: here there IS a declared space and demoting corrupts it."""
    from memory import reembed
    _sin_ollama_a_tiempo(monkeypatch)
    monkeypatch.setattr(reembed, "stored_signature", lambda: "ollama:embeddinggemma:768")
    emb.reset()

    assert emb.active_backend() == "ollama", (
        "con la BD sellada embeddinggemma, degradar busca esos vectores con consultas de 384 rellenadas a 768 "
        "y en SILENCIO: exactamente el fallo que a V2-103 le costó una auditoría")
    assert emb._resolved_at == 0.0, "y se re-sondea en la próxima llamada, no dentro de 5 minutos"


def test_ante_la_DUDA_se_defiende(monkeypatch):
    """If the signature cannot be read, we do not know whether there is anything to protect. The asymmetry is
    deliberate: demoting too much corrupts SILENTLY; preserving too much costs lexical recall, which is visible and passes."""
    from memory import reembed
    _sin_ollama_a_tiempo(monkeypatch)
    monkeypatch.setattr(reembed, "stored_signature",
                        lambda: (_ for _ in ()).throw(OSError("disco ilegible")))
    emb.reset()
    assert emb.active_backend() == "ollama"
