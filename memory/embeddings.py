"""memory/embeddings.py — embeddings LOCALES para la memoria (V2-002 · T46).

Se calculan **al insertar** (en el writer) y **al consultar** (en el retriever). Cadena de backends, de mejor
a más disponible, resuelta perezosamente y cacheada:

  1. **Ollama** — `embeddinggemma` (768 dims, multilingüe → bueno para castellano), on-device, sin coste por
     inserción. Modelo/host por env (`ZAELAR_EMBED_MODEL` / `ZAELAR_EMBED_HOST`); fallback de modelo
     `nomic-embed-text`. Es el backend por defecto si Ollama responde.
  2. **fastembed** — ONNX-Runtime, sin server/GPU. Solo si el paquete está instalado.
  3. **hashing determinista** — feature-hashing bag-of-words a `EMBED_DIM` dims, L2-normalizado. SIEMPRE
     disponible (cero deps, cero red) → los tests y los entornos sin Ollama nunca se quedan sin embeddings.
     Da señal LÉXICA (textos que comparten palabras quedan más cerca), no semántica profunda.

Todos los vectores se **L2-normalizan** → la distancia L2 de sqlite-vec se comporta como similitud coseno.
El vector siempre tiene dimensión `schema.EMBED_DIM` (768): se trunca/rellena si un backend devuelve otra.

**Regla de modelo por invocación**: aquí el modelo de embeddings tiene un DEFAULT configurable por env; no fija
ninguna env global que fuerce a los cerebros. Es una elección de infraestructura de la memoria, no del cerebro.
"""
import hashlib
import json
import logging
import math
import os
import re
import urllib.request

from .schema import EMBED_DIM

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
logger = logging.getLogger("zaelar.memory.embeddings")


def _warn_if_degraded(backend: str, forced: bool) -> None:
    """T176 — la memoria por SIGNIFICADO depende críticamente del backend: embeddinggemma (Ollama) aguanta a escala;
    el fallback fastembed COLAPSA con miles de recuerdos y 'hash' es solo-léxico. Si caemos a un backend degradado
    la superpotencia se pierde EN SILENCIO → avisamos una vez (visible en logs/diagnóstico)."""
    if backend == "ollama":
        return
    src = "forzado por ZAELAR_EMBED_BACKEND" if forced else "Ollama/embeddinggemma NO disponible"
    if backend == "hash":
        logger.warning("⚠️ memoria: embeddings en 'hash' (%s) — recall SEMÁNTICO prácticamente DESACTIVADO "
                       "(solo FTS léxico). Arranca Ollama con embeddinggemma para memoria por significado.", src)
    else:  # fastembed u otro
        logger.warning("⚠️ memoria: embeddings en '%s' (%s) — recall semántico DEGRADADO a escala (colapsa con "
                       "miles de recuerdos, T176). Recomendado: Ollama + embeddinggemma.", backend, src)


# ── backend activo (resuelto una vez, con re-intento si quedó DEGRADADO) ──────────────────────────────────────
_backend: str | None = None      # 'ollama' | 'fastembed' | 'hash'
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


def _ollama_embed(texts: list[str]) -> list[list[float]] | None:
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
            with urllib.request.urlopen(req, timeout=float(os.getenv("ZAELAR_EMBED_TIMEOUT", "20"))) as r:
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
            _note_ollama_outcome(busy=False)
            return embs
        _note_ollama_outcome(busy=_looks_busy(data.get("error")))
    except Exception as ex:  # noqa: BLE001
        # A 4xx/5xx arrives here as an HTTPError whose BODY carries Ollama's reason, and the reason is the whole
        # question: "server busy" is a queue that will drain, "connection refused" is a server that is not there.
        _note_ollama_outcome(busy=_looks_busy(_error_body(ex)))
        return None
    return None


_BUSY_MARKERS = ("server busy", "maximum pending requests", "overloaded", "too many requests")
_ollama_busy = False            # last outcome was "alive but saturated", not "absent"


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

            _fastembed_model = TextEmbedding()
        return [list(map(float, v)) for v in _fastembed_model.embed(texts)]
    except Exception:
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
        if _forced or _backend == "ollama":
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
    forced = cfg_val or os.getenv("ZAELAR_EMBED_BACKEND")  # 'ollama'|'fastembed'|'hash'|… — UI/tests/power-user
    if forced in ("auto", ""):
        forced = None                               # 'auto' = autodetección (ollama→fastembed→hash), no forzar
    if forced:
        _backend = forced
        _forced = True
        _resolved_at = _t.time()
        _warn_if_degraded(_backend, forced=True)
        return
    _forced = False
    prev = _backend
    if _ollama_embed(["ping"]) is not None:
        _backend = "ollama"
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
    """Devuelve el backend en uso ('ollama'|'fastembed'|'hash'). Resuelve perezosamente. Para tests/diagnóstico."""
    _resolve_backend()
    return _backend  # type: ignore


def reset():
    """Olvida el backend resuelto (tests que cambian env)."""
    global _backend, _fastembed_model, _active_dim, _resolved_at, _forced
    _backend = None
    _fastembed_model = None
    _active_dim = None
    _resolved_at = 0.0
    _forced = False


def _active_model_name() -> str:
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
    if _backend == "ollama":
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
    name = _active_model_name().lower()
    for k, d in _MODEL_DIMS.items():
        if k in name:
            _active_dim = d
            return _active_dim
    # desconocido → probe: la longitud REAL del primer vector manda.
    probe = _ollama_embed(["x"]) if _backend == "ollama" else (_fastembed_embed(["x"]) if _backend == "fastembed" else None)
    _active_dim = len(probe[0]) if probe else EMBED_DIM
    return _active_dim
