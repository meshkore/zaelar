"""memory/embeddings.py — the memory's embeddings (V2-002 · T46; CLOUD provider since V2-501).

Computed **on insert** (in the writer) and **on query** (in the retriever). Backends, from the titular to the
always-available one, resolved lazily and cached:

  1. **cloud, OpenAI `/embeddings` protocol** — the TITULAR (`config/models.default.json` §embeddings:
     `text-embedding-3-small`, 768 dims requested via `dimensions`). It is the only one that runs identically
     on a laptop and inside a Fly container, which is the operator's rule: *local must measure what the cloud
     measures*. Chosen by measurement, not by catalogue — the numbers are in that row's `why`.
  2. **Ollama** — `embeddinggemma`. NO LONGER THE DEFAULT: it is a local server, it does not exist in the
     cloud, and an install using it measured something other than the cloud did. Kept because databases are
     sealed with its signature and because a self-hoster with a GPU may prefer it (chosen in the panel).
  3. **fastembed** — ONNX-Runtime, no server. A safety net, NOT a titular: its default model
     (`BAAI/bge-small-en-v1.5`) is ENGLISH ONLY and scores 7/12 on Spanish recall where the titular scores 12.
  4. **deterministic hashing** — feature-hashing into `EMBED_DIM` dims, L2-normalised. ALWAYS available (no
     deps, no network) → tests and bare environments are never left without a vector. LEXICAL signal only.

Every vector is **L2-normalised** → sqlite-vec's L2 distance behaves like cosine similarity. The vector always
has the ACTIVE backend's dimension; it is truncated/padded if a backend returns another.

**A titular failure NEVER changes the space.** Neither a saturated Ollama nor a 429 from the cloud provider
demotes the process: the call fails, `last_degraded` says so, the writer defers the vector (`embed_pending`,
repaired by REM) and the reader drops to lexical. Swapping the space in flight is the defect V2-103 cost.

**Model-per-invocation rule**: the embedding model has a configurable default here; it sets no global env that
would force the brains. It is memory infrastructure, not a brain's choice.
"""
import hashlib
import json
import logging
import math
import os
import re
import socket
import urllib.request

from .schema import EMBED_DIM

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
logger = logging.getLogger("zaelar.memory.embeddings")


# Backends that are a legitimate operator CHOICE (not a fault). Anything else is degradation: the titular did
# not answer and we are producing a WORSE signal than the one the database is indexed with.
_HEALTHY = ("cloud", "ollama")


def _warn_if_degraded(backend: str, forced: bool) -> None:
    """T176 — recall BY MEANING depends critically on the backend: the cloud titular and embeddinggemma hold up
    at scale; the fastembed fallback COLLAPSES with thousands of memories (and is English-only on top of that)
    and 'hash' is lexical-only. If we drop to a degraded backend the superpower is lost IN SILENCE → warn once."""
    if backend in _HEALTHY:
        return
    src = "forced by ZAELAR_EMBED_BACKEND" if forced else "the titular provider is NOT available"
    if backend == "hash":
        logger.warning("⚠️ memory: embeddings on 'hash' (%s) — SEMANTIC recall practically DISABLED (lexical FTS "
                       "only). Check the embedding provider's credential.", src)
    else:  # fastembed or other
        logger.warning("⚠️ memory: embeddings on '%s' (%s) — semantic recall DEGRADED (collapses at scale and its "
                       "default model is English-only, T176).", backend, src)
    _report_degraded(backend, forced)


def _report_degraded(backend: str, forced: bool) -> None:
    """Y ADEMÁS del log, ÁMBAR — porque este módulo escribe con `logging` de la stdlib, no con loguru, así que
    sus líneas salen sin marca de tiempo y en medio del ruido del arranque (auditoría 2026-08-23, H7).

    La regla ya está pagada tres veces en esta casa: *un fallo de la memoria nunca puede quedarse en un
    `logger.warning`*. El gemelo es el canal de paráfrasis mudo, que desde el 2026-08-18 pone la salud en ámbar
    cuando hubo candidatos y no salió ni uno. Aquí la pérdida es MAYOR y más silenciosa: con `hash` el recall
    por significado queda prácticamente apagado —solo FTS léxico— y nada en pantalla lo dice, así que la memoria
    parece funcionar y simplemente deja de encontrar lo que no coincide literalmente.

    **Un backend FORZADO no es una avería**: `ZAELAR_EMBED_BACKEND` lo pone la suite en cada corrida y ponerlo
    ámbar dejaría el semáforo permanentemente sucio, que es como se aprende a ignorarlo. Solo se reporta el
    degradado que NADIE pidió.
    """
    if forced:
        return
    try:
        from voice import health_state
        health_state.record("memory", "degraded",
                            f"embeddings on '{backend}': the titular provider is not available — "
                            f"recall by meaning {'DISABLED' if backend == 'hash' else 'degraded'}")
    except Exception:  # noqa: BLE001
        pass  # la observabilidad NUNCA rompe la memoria


# ── backend activo (resuelto una vez, con re-intento si quedó DEGRADADO) ──────────────────────────────────────
_backend: str | None = None      # 'cloud' | 'ollama' | 'fastembed' | 'hash'
_fastembed_model = None
_active_dim: int | None = None   # dim del modelo ACTIVO (V2-031: provider-driven, ya no fijo a 768)
_resolved_at: float = 0.0        # cuándo se resolvió `_backend` por última vez (para el re-intento)
_forced: bool = False            # True = vino de config/env explícito → nunca se re-intenta (respeta al operador)

# V2-103 (2026-08-16): un hipo TRANSITORIO de Ollama justo al arrancar el proceso resolvía `_backend` a
# 'fastembed'/'hash' y lo dejaba CACHEADO ahí toda la vida del proceso (auditoría en vivo: dos hechos idénticos
# duplicados porque el dedup semántico —solo calibrado para 'ollama'— y la reparación nocturna de vectores
# —autoexcluida por firma discordante— quedaron apagados durante toda la sesión aunque Ollama se recuperase
# segundos después). Solo se re-intenta si la resolución fue AUTOMÁTICA (nunca pisa un `embed_provider`/
# `ZAELAR_EMBED_BACKEND` explícito) y el backend actual está DEGRADADO (≠ 'ollama') — un backend sano no genera
# tráfico extra a Ollama en cada inserción.
_BACKEND_RECHECK_S = float(os.getenv("ZAELAR_EMBED_RECHECK_S", "300"))

# Dim conocida por modelo (evita una probe de red). Substring-match sobre el nombre. Los desconocidos se resuelven
# por la longitud REAL del primer vector. embeddinggemma/nomic=768; la familia SOTA multilingüe de 1024 (bge-m3,
# e5-large, arctic-l, mxbai, qwen3-embedding-0.6B) sube el techo de recall (V2-031 T1).
_MODEL_DIMS = {
    "embeddinggemma": 768, "nomic-embed-text": 768, "all-minilm": 384,
    "bge-m3": 1024, "bge-large": 1024, "multilingual-e5-large": 1024, "e5-large": 1024,
    "snowflake-arctic-embed-l": 1024, "arctic-embed-l": 1024, "mxbai-embed-large": 1024,
    "qwen3-embedding": 1024,
}


def _mem_cfg() -> dict:
    """Config de recuperación de la memoria (sección `memory` de config/v2): store > env (V2-030). El store MANDA
    sobre `.env`; sin config disponible (tests aislados) caemos a env directo."""
    try:
        from config import v2 as _v2
        return _v2.get("memory")
    except Exception:
        return {}


def _ollama_host() -> str:
    return os.getenv("ZAELAR_EMBED_HOST") or os.getenv("OLLAMA_HOST") or "http://localhost:11434"


def _ollama_model() -> str:
    # store (UI) > env > default. Cambiar el modelo EXIGE re-embed (memory/reembed.py) — no mezclar espacios.
    return (str(_mem_cfg().get("embed_model") or "").strip()
            or os.getenv("ZAELAR_EMBED_MODEL") or "embeddinggemma")


def _ollama_embed(texts: list[str], *, timeout: float | None = None) -> list[list[float]] | None:
    """`timeout=None` → el presupuesto de una llamada REAL (`ZAELAR_EMBED_TIMEOUT`, 20 s). La SONDA de
    resolución pasa el suyo, mucho más corto: son dos preguntas distintas (V2-349)."""
    global _ollama_timeout
    try:
        # keep_alive: mantén el modelo de embedding RESIDENTE en Ollama. El CORAZÓN de memoria
        # (`qwen2.5:14b`, off-hot-path tras cada turno) puede DESALOJAR embeddinggemma de la VRAM Metal → el
        # siguiente recall pagaría la RECARGA del modelo (~4s, medido en el turno vivo). Con keep_alive largo,
        # el embedding de la query en la ruta caliente no paga reload. Configurable (ZAELAR_EMBED_KEEP_ALIVE).
        _payload = {"model": _ollama_model(), "input": texts,
                    "keep_alive": os.getenv("ZAELAR_EMBED_KEEP_ALIVE", "30m")}
        req = urllib.request.Request(
            _ollama_host().rstrip("/") + "/api/embed",
            data=json.dumps(_payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        import time as _t
        _t0 = _t.time()
        # FASE 3: marca CONTENCIÓN mientras el embed bloquea (GPU Ollama) → el turno de voz correlaciona su TTFT.
        try:
            from voice.observer import mark_busy as _mb
        except Exception:
            _mb = None
        if _mb:
            _mb("embed", True)
        try:
            # Una llamada REAL merece los 20 s: esperar es mejor que degradar el espacio. PERO si la última
            # vez Ollama no contestó a tiempo, ya sabemos que no está respondiendo, y volver a esperar 20 s
            # por llamada convierte el acierto de conservar el espacio en un turno muerto — justo la latencia
            # que V2-311 midió. Mientras dure ese estado, las llamadas reales usan también el reloj corto:
            # el espacio se conserva igual, el vector de ESA llamada se difiere (que es lo que ya hace la
            # rama de saturación), y el primer sondeo que responda restaura el presupuesto entero.
            _presupuesto = (timeout if timeout is not None
                            else (probe_budget_s() if _ollama_timeout
                                  else float(os.getenv("ZAELAR_EMBED_TIMEOUT", "20"))))
            with urllib.request.urlopen(req, timeout=_presupuesto) as r:
                data = json.load(r)
        finally:
            if _mb:
                _mb("embed", False)
        # PERF (V2-037): el embedding es una llamada BLOQUEANTE a Ollama (GPU) — puede contender con STT/voz. Visible
        # en System Events. Best-effort (no romper si el observer no está).
        try:
            from voice.observer import perf
            perf(f"embed {_ollama_model()} ×{len(texts)} {round((_t.time()-_t0)*1000)}ms",
                 module="memory", func="embeddings._ollama_embed", ms=(_t.time() - _t0) * 1000)
        except Exception:
            pass
        embs = data.get("embeddings")
        if embs and len(embs) == len(texts):
            _ollama_timeout = False          # contestó: se acabó el reloj corto, vuelve el presupuesto entero
            _note_ollama_outcome(busy=False)
            return embs
        _note_ollama_outcome(busy=_looks_busy(data.get("error")))
    except Exception as ex:  # noqa: BLE001
        # A 4xx/5xx arrives here as an HTTPError whose BODY carries Ollama's reason, and the reason is the whole
        # question: "server busy" is a queue that will drain, "connection refused" is a server that is not there.
        # And a TIMEOUT is a THIRD answer, not a flavour of the second (V2-349): it means «I don't know yet» —
        # Ollama may be perfectly alive with the GPU held by the CORAZÓN. Treating it as absence is what makes
        # a short probe dangerous, because absence DEMOTES the whole process and demoting CHANGES THE VECTOR
        # SPACE (see the busy branch in `_resolve_backend`). So it gets its own flag.
        _ollama_timeout = isinstance(ex, (TimeoutError, socket.timeout)) or "timed out" in str(ex).lower()
        _note_ollama_outcome(busy=_looks_busy(_error_body(ex)))
        return None
    return None


_BUSY_MARKERS = ("server busy", "maximum pending requests", "overloaded", "too many requests")
_ollama_busy = False            # last outcome was "alive but saturated", not "absent"
_ollama_timeout = False         # last outcome was "did not answer in time" — which is not "absent" either

#: El reloj de la SONDA de resolución, separado del de una llamada real (V2-349). Preguntar «¿estás ahí?» y
#: pedir un embedding de verdad no son la misma pregunta y no merecen el mismo presupuesto: la primera bloquea
#: el PRIMER acceso a memoria de un proceso nuevo (la crea el DDL de la tabla vectorial, que necesita la
#: dimensión), y la segunda está en la ruta caliente de un turno donde esperar es mejor que degradar.
_PROBE_ENV = "ZAELAR_EMBED_PROBE_TIMEOUT"
_PROBE_DEFAULT_S = 1.5


def _indexed_space_to_defend() -> bool:
    """¿Hay un espacio vectorial INDEXADO que proteger? (V2-350, 2026-08-27)

    «Un timeout no es una ausencia» (V2-349) conserva `ollama` cuando la sonda se queda sin tiempo, para no
    degradar el proceso a fastembed y buscar vectores embeddinggemma con consultas de 384 rellenadas a 768. Esa
    regla es verdadera **cuando hay algo que corromper**, y estaba mal acotada: en una BD sin sellar y sin
    vectores no protege nada y cuesta el canal semántico entero.

    Medido en el plató del arnés (ronda 13, 2026-08-27): el workspace ES tenía 6 píldoras, 1 vector y NINGÚN
    `.embedsig`, y cada recall salía «recall on FTS only». Ahí fastembed habría dado recall semántico REAL y
    coherente consigo mismo. El workspace US, en cambio, SÍ trae firma (`ollama:embeddinggemma:768`) — y ahí
    conservar es exactamente lo correcto, que es el caso que protege V2-103.

    La firma es la respuesta EXACTA a la pregunta: es la declaración de con qué está indexada esta BD. Sin ella,
    `space_ok()` ya hace fail-open («base nueva, asume coherente»), así que no hay veredicto que defender.

    Ante la DUDA se defiende. La asimetría es deliberada: degradar de más corrompe en SILENCIO (V2-103), y
    conservar de más cuesta un recall léxico, que se ve y se pasa."""
    try:
        from . import reembed as _reembed          # perezoso: `reembed` importa este módulo
        return _reembed.stored_signature() is not None
    except Exception:  # noqa: BLE001
        return True


def probe_budget_s() -> float:
    try:
        return max(0.1, float(os.getenv(_PROBE_ENV, str(_PROBE_DEFAULT_S))))
    except Exception:
        return _PROBE_DEFAULT_S


def _looks_busy(detail) -> bool:
    return any(m in str(detail or "").lower() for m in _BUSY_MARKERS)


def _error_body(ex: Exception) -> str:
    """Ollama's reason lives in the HTTPError's body, which is readable exactly once."""
    try:
        return ex.read().decode("utf-8", "replace")[:300]      # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return str(ex)


def _note_ollama_outcome(*, busy: bool) -> None:
    global _ollama_busy
    _ollama_busy = bool(busy)


def _fastembed_embed(texts: list[str]) -> list[list[float]] | None:
    global _fastembed_model
    try:
        if _fastembed_model is None:
            from fastembed import TextEmbedding  # type: ignore

            from . import model_cache
            # Mismo motivo que en `rerank_local.py`: sin `cache_dir` el modelo cae en el TEMP del sistema, que
            # se purga — y este es el fallback de embeddings, o sea el recall por SIGNIFICADO volviendo a frío
            # sin que nadie lo relacione con una caché. Ver `model_cache.py`.
            cache = model_cache.models_dir()
            _fastembed_model = TextEmbedding(**({"cache_dir": cache} if cache else {}))
        return [list(map(float, v)) for v in _fastembed_model.embed(texts)]
    except Exception:
        return None


# ── CLOUD backend (OpenAI `/embeddings` protocol) ─────────────────────────────────────────────────────────────
# Models that accept `dimensions` (matryoshka): a SHORTER vector can be requested without losing quality.
# Measured 2026-08-29 over 12 ES+EN queries: 768 dims scores 12/12 with a +0.204 margin and 1536 scores 12/12
# with +0.201 — so asking for 768 costs nothing and fits the `EMBED_DIM` the vector table is already created
# with, which means adopting the new provider does NOT force a schema migration on anybody.
_MATRYOSHKA = ("text-embedding-3",)


def _cloud_base_url() -> str:
    return (str(_mem_cfg().get("embed_base_url") or "").strip()
            or os.getenv("ZAELAR_EMBED_BASE_URL") or "https://api.openai.com/v1")


def _cloud_model() -> str:
    # store (panel) > env > default. Changing the model REQUIRES a re-embed (memory/reembed.py) — never mix spaces.
    return (str(_mem_cfg().get("embed_model") or "").strip()
            or os.getenv("ZAELAR_EMBED_MODEL") or "text-embedding-3-small")


def _cloud_key() -> str:
    """The credential, BY NAME, read from the table itself (the `key_env` of the `embeddings` row).

    The tempting move was to call `nucleo.provider_keys`, the house endpoint→variable resolver. We do not, and
    not for tidiness: `memory/` does not import `nucleo/` (guarded by `test_memory_owes_nucleo_nothing`),
    because the memory has to exist without a brain. And it turns out no resolver is needed here: the table
    ALREADY says what pays for this row, so it is read where it is already written instead of inferred from the
    URL.

    CONTRACT for anyone changing the endpoint from the panel: if you point `embed_base_url` at another
    provider, put its key in `embed_api_key` too. It is not guessed — guessing is how one provider's key gets
    sent to another's host, which already cost this house two days of silent 401s.
    """
    inline = str(_mem_cfg().get("embed_api_key") or "").strip()
    if inline:
        return inline
    env_name = "OPENAI_API_KEY"
    try:
        from config import models as _table
        env_name = str((_table.rungs("embeddings")[0] or {}).get("key_env") or "") or env_name
    except Exception:  # noqa: BLE001
        pass
    return os.getenv(env_name, "")


def _cloud_dims() -> int | None:
    """Dims to REQUEST, or None if the model does not accept the parameter (then its native dim rules)."""
    return EMBED_DIM if any(m in _cloud_model().lower() for m in _MATRYOSHKA) else None


def _cloud_embed(texts: list[str], *, timeout: float | None = None) -> list[list[float]] | None:
    """POST `{base_url}/embeddings`. Returns None on ANY failure — and returning None is a decision, not an
    omission: the caller turns it into `last_degraded`, the writer defers the vector and the database's space
    stays as it is. A 429 must never become a change of vector space (V2-103)."""
    key = _cloud_key()
    if not key:
        return None
    body: dict = {"model": _cloud_model(), "input": list(texts)}
    dims = _cloud_dims()
    if dims:
        body["dimensions"] = dims
    req = urllib.request.Request(
        _cloud_base_url().rstrip("/") + "/embeddings",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or float(os.getenv("ZAELAR_EMBED_TIMEOUT_S", "20"))) as r:
            data = json.loads(r.read().decode("utf-8"))
        rows = sorted(data["data"], key=lambda it: it.get("index", 0))
        out = [list(map(float, it["embedding"])) for it in rows]
        if len(out) != len(texts):
            return None
        # THE BILLING GATE. Deferred import, and it is a deliberate exception to "memory/ does not import
        # nucleo/" — the same trade already written down for `memory/rerank.py`: a register-a-callback design
        # reopens the hole for any process that forgets to register, and what leaks through that hole is real
        # money, silently. Here the argument is stronger than for the reranker, which is dormant: this runs on
        # every insert AND every query. Metering never takes down the metered (V2-097), hence the swallow.
        try:
            from nucleo.energy_meter import meter_openai_response
            meter_openai_response(data, base_url=_cloud_base_url(), model=_cloud_model())
        except Exception:  # noqa: BLE001
            pass
        return out
    except Exception as e:  # noqa: BLE001
        logger.debug("cloud embeddings failed: %s", _error_body(e) or e)
        return None


def _hash_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Feature-hashing bag-of-words → vector determinista de `dim` dims. Señal léxica, cero deps/red."""
    vec = [0.0] * dim
    for tok in _TOKEN_RE.findall(text.lower()):
        h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "little") % dim
        sign = 1.0 if (h[4] & 1) else -1.0
        vec[idx] += sign
    return vec


def _fit_dim(vec: list[float], dim: int = EMBED_DIM) -> list[float]:
    if len(vec) == dim:
        return vec
    if len(vec) > dim:
        return vec[:dim]
    return vec + [0.0] * (dim - len(vec))


def _l2_normalize(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec))
    if n <= 1e-12:
        return vec
    return [x / n for x in vec]


def _resolve_backend():
    global _backend, _resolved_at, _forced
    import time as _t
    if _backend is not None:
        # Re-intento (V2-103): solo si la resolución fue AUTOMÁTICA, el backend actual está DEGRADADO (no
        # 'ollama') y ya pasó el TTL — nunca pisa una elección explícita, nunca re-sondea un backend sano.
        if _forced or _backend in _HEALTHY:
            return
        if (_t.time() - _resolved_at) < _BACKEND_RECHECK_S:
            return
        # cae al re-sondeo de abajo (no retornamos)
    # store (UI, sección `memory.embed_provider`) > env `ZAELAR_EMBED_BACKEND` > autodetección. 'ollama' (default)
    # es local; los proveedores cloud (voyage/openai) se enchufan aquí sin tocar el resto (V2-030).
    #
    # BUG real, cazado 2026-08-17 en validación con coste real (el operador pidió evitar Ollama y el env var no
    # lo hacía): `config/v2.json` trae `embed_provider="auto"` de fábrica — un string NO VACÍO, así que el `or`
    # de abajo lo tomaba como valor de config y JAMÁS llegaba a mirar `ZAELAR_EMBED_BACKEND` (el "auto"→None de
    # la línea siguiente llegaba demasiado tarde: normalizaba el valor de CONFIG, no decidía si consultar el
    # env). Con Ollama disponible, esto hacía que el env var fuera aire — la autodetección ganaba en silencio.
    # Fix: cada fuente se normaliza "auto"/""→vacío ANTES del `or`, así un "auto" explícito en config SÍ cede
    # el turno al env var, como ya decía el comentario de precedencia (que nunca se cumplía del todo).
    cfg_val = str(_mem_cfg().get("embed_provider") or "").strip()
    if cfg_val == "auto":
        cfg_val = ""
    forced = cfg_val or os.getenv("ZAELAR_EMBED_BACKEND")  # 'openai'|'ollama'|'fastembed'|'hash'|… — UI/tests
    if forced in ("auto", ""):
        forced = None                               # 'auto' = autodetect (cloud→ollama→fastembed→hash)
    # The PROVIDER name in the table is 'openai' (that is its protocol); the internal backend is called 'cloud'
    # because any compatible endpoint serves. One alias, here, so the `.embedsig` signature does not depend on
    # how the provider happened to be spelled in the panel.
    if forced in ("openai", "cloud", "azure", "voyage"):
        forced = "cloud"
    if forced:
        _backend = forced
        _forced = True
        _resolved_at = _t.time()
        _warn_if_degraded(_backend, forced=True)
        return
    _forced = False
    prev = _backend
    # The busy flag describes THIS probe and nothing else. Left over from a previous call it would decide with
    # stale information — and it showed up as an order-dependent test failure, which is the shape of bug that
    # passes locally and fails in CI: a probe that never reaches `_ollama_embed` (or a mocked one) would inherit
    # someone else's verdict. Cleared here so the only way it becomes true is this probe saying so.
    global _ollama_busy, _ollama_timeout
    _ollama_busy = False
    _ollama_timeout = False
    # La SONDA lleva su propio reloj (V2-349). Medido el 2026-08-26: el PRIMER acceso a memoria de un proceso
    # fresco costaba **20,8 s** —lo paga el DDL de la tabla vectorial, que necesita `dim()`— porque esta sonda
    # usaba el presupuesto de una llamada REAL (20 s) contra un Ollama vivo pero con la GPU ocupada. La consulta
    # en sí tarda 25 ms; el arnés lo estaba midiendo como «la memoria tarda 10 s en no encontrar nada».
    # The CLOUD comes first: it is the table's titular and the only backend that exists identically on a laptop
    # and inside a container. Probed only if a credential is present — without one there is nothing to test and
    # the probe would be a request guaranteed to fail on every boot.
    if _cloud_key() and _cloud_embed(["ping"], timeout=probe_budget_s()) is not None:
        _backend = "cloud"
    elif _ollama_embed(["ping"], timeout=probe_budget_s()) is not None:
        _backend = "ollama"
    elif _ollama_timeout and _indexed_space_to_defend():
        # UN TIMEOUT NO ES UNA AUSENCIA, y esto es lo que hace SEGURO acortar la sonda. Con 20 s, una petición
        # encolada detrás del CORAZÓN podía llegar a tiempo; con 1,5 s no llegaría, y el camino de antes la
        # habría leído como «Ollama no está» → fastembed → 384 dims rellenados a 768 contra un índice sellado
        # embeddinggemma:768. O sea que abaratar la sonda, tal cual, habría comprado 19 s a cambio de
        # CAMBIAR EL ESPACIO VECTORIAL más a menudo: el fallo que V2-103 tardó una auditoría en encontrar.
        # Así que un reloj agotado se comporta como la saturación: se conserva el espacio, se difiere el vector
        # y se re-sondea en la llamada siguiente. Lo que SÍ degrada sigue siendo un fallo definitivo y rápido
        # (conexión rechazada, 404), que es información de verdad y llega en milisegundos.
        _backend = "ollama"
        logger.info("memoria: Ollama no respondió a la sonda en %.1fs (no ausente) — se conserva el espacio "
                    "vectorial y se re-sondea en la próxima llamada", probe_budget_s())
        _resolved_at = 0.0
        _warn_if_degraded(_backend, forced=False)
        return
    elif _ollama_busy:
        # BUSY IS NOT ABSENT (2026-08-19). Reproduced live: `/api/embed` answering
        # `{"error":"server busy, please try again.  maximum pending requests exceeded"}` while `/api/tags` served
        # fine and `embeddinggemma:latest` was pulled. The probe read that as "Ollama is gone" and demoted the
        # WHOLE PROCESS to fastembed for `_BACKEND_RECHECK_S` (300s) — and demoting is not a smaller version of
        # the same thing, it CHANGES THE VECTOR SPACE: fastembed is 384 dims padded to 768 against an index
        # stamped embeddinggemma:768, so for five minutes the writer refuses to store vectors (V2-103
        # `_mark_embed_pending`) and the reader drops its vector channels (the space guard in `retriever.search`).
        # This is the root cause behind both of those guards, and behind the 51.6% vector-less rows the V2-103
        # audit found.
        #
        # So a saturated Ollama DEFERS rather than demotes: the backend stays `ollama`, the individual call fails
        # (which `embed_batch` already reports as `last_degraded`, so reads go lexical and writes queue for REM's
        # `repair_embeddings`), and the space stays what the index says it is. The recovery is also immediate
        # instead of five minutes late — `_resolved_at` is left in the past on purpose so the very next call
        # re-probes, because a drained queue can happen a second later.
        _backend = "ollama"
        logger.info("memoria: Ollama SATURADO (no ausente) — se conserva el espacio vectorial y se difiere el "
                    "vector; se re-sondea en la próxima llamada")
        _resolved_at = 0.0
        _warn_if_degraded(_backend, forced=False)
        return
    elif _fastembed_embed(["ping"]) is not None:
        _backend = "fastembed"
    else:
        _backend = "hash"
    _resolved_at = _t.time()
    if prev is not None and prev != _backend:
        logger.info("memoria: backend de embeddings pasó de '%s' a '%s' tras re-intento", prev, _backend)
    _warn_if_degraded(_backend, forced=False)


def active_backend() -> str:
    """Backend in use ('cloud'|'ollama'|'fastembed'|'hash'). Resolved lazily. For tests/diagnostics."""
    _resolve_backend()
    return _backend  # type: ignore


def reset():
    """Olvida el backend resuelto (tests que cambian env)."""
    global _backend, _fastembed_model, _active_dim, _resolved_at, _forced, _ollama_busy, _ollama_timeout
    _backend = None
    _fastembed_model = None
    _active_dim = None
    _resolved_at = 0.0
    _forced = False
    # Las dos banderas de VEREDICTO se van con el backend (V2-349). Una `_ollama_timeout` heredada no es un
    # detalle de tests: dejaría las llamadas REALES con el reloj corto para siempre, decidiendo con el
    # veredicto de otro. Es la misma trampa que ya documenta `_ollama_busy` en `_resolve_backend`, y la cazó
    # la suite existente en cuanto nació la bandera.
    _ollama_busy = False
    _ollama_timeout = False


def _active_model_name() -> str:
    if _backend == "cloud":
        return _cloud_model()
    if _backend == "ollama":
        return _ollama_model()
    # ⚠️ KNOWN MISLABEL, deliberately left alone (2026-08-18). For the fastembed backend this returns the config's
    # `embed_model`, which names the OLLAMA model — but `_fastembed_embed` calls `TextEmbedding()` with no
    # arguments and loads fastembed's own default (`BAAI/bge-small-en-v1.5`, 384 dims, padded to 768 by
    # `_fit_dim`). So the signature reads "fastembed:embeddinggemma:768": a label naming a model that is not
    # running. It never causes a FALSE space mismatch — the `backend` half already differs from `ollama:…` —
    # which is exactly why it survived this long.
    #
    # The obvious fix (return the real loaded name) was tried and REVERTED, because the name is load-bearing for
    # something else: `dim()` resolves the active dimension by matching this string against `_MODEL_DIMS`, so a
    # truthful name stops matching, falls through to the real probe, and moves the fastembed dimension 768 -> 384.
    # That is arguably more correct — bge-small IS 384, and padding doubles the brute-force scan for nothing — but
    # it is a vector-space MIGRATION, not a label change, and it broke `test_vec_search_smoke` immediately (a
    # 768-dim vector into a 384-dim vec0 table). Fixing it properly means deciding what happens to a DB already
    # indexed at 768 with this backend, which is its own task.
    # Until then, callers that need the truth for REPORTING derive it themselves (see the LoCoMo adapter's
    # `declarations()`), and nothing that decides behavior depends on the wrong string.
    if _backend == "fastembed":
        return str(_mem_cfg().get("embed_model") or os.getenv("ZAELAR_EMBED_MODEL") or "")
    return ""


# ── API pública ─────────────────────────────────────────────────────────────────────────────────────────
# Flag OBSERVABLE de la última llamada (auditoría 2026-07-19 P0-1): si el backend cayó en caliente y se degradó a
# hash, el llamador (writer) debe SABERLO — un vector hash insertado en el índice semántico es mezcla de espacios
# permanente y sin traza. El writer lo consulta y, si hubo degradación, NO inserta el vector (marca embed_pending).
last_degraded: bool = False


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embeddings de una lista de textos. Siempre devuelve vectores de EMBED_DIM, L2-normalizados.
    Si el backend real falla, degrada a hash SOLO como valor de retorno (p. ej. para una query puntual) y lo
    señala en `last_degraded` — el índice persistente nunca debe recibir esos vectores."""
    global last_degraded
    if not texts:
        return []
    _resolve_backend()
    d = dim()
    out: list[list[float]] | None = None
    if _backend == "cloud":
        out = _cloud_embed(texts)
    elif _backend == "ollama":
        out = _ollama_embed(texts)
    elif _backend == "fastembed":
        out = _fastembed_embed(texts)
    # SOLO la caída EN CALIENTE es degradación (backend real que falla → hash de emergencia). Un backend 'hash'
    # CONFIGURADO (tests/dev) es su propio espacio consistente — lo gobierna la firma embedsig, no este flag.
    last_degraded = out is None and _backend != "hash"
    if out is None:  # backend hash configurado, o caída en caliente → hashing determinista (a la dim activa)
        out = [_hash_embed(t, d) for t in texts]
    return [_l2_normalize(_fit_dim(v, d)) for v in out]


def embed(text: str) -> list[float]:
    """Embedding de un texto → vector de EMBED_DIM (L2-normalizado)."""
    return embed_batch([text])[0]


def dim() -> int:
    """Dimensión del embedding ACTIVO (V2-031: provider-driven). Registry por nombre → probe real → default 768.
    Se cachea (`reset()` la olvida). El schema de `vec_memories` y `reembed` la usan para crear la tabla vec."""
    global _active_dim
    if _active_dim is not None:
        return _active_dim
    _resolve_backend()
    if _backend == "hash":
        _active_dim = EMBED_DIM
        return _active_dim
    if _backend == "cloud":
        # For a matryoshka model WE decide the dim by asking for it — reading it from a registry by name would
        # guess the native one (1536) while the arriving vector is 768 wide.
        d = _cloud_dims()
        if d:
            _active_dim = d
            return _active_dim
    name = _active_model_name().lower()
    for k, d in _MODEL_DIMS.items():
        if k in name:
            _active_dim = d
            return _active_dim
    # desconocido → probe: la longitud REAL del primer vector manda.
    probe = (_cloud_embed(["x"]) if _backend == "cloud"
             else _ollama_embed(["x"]) if _backend == "ollama"
             else _fastembed_embed(["x"]) if _backend == "fastembed" else None)
    _active_dim = len(probe[0]) if probe else EMBED_DIM
    return _active_dim
