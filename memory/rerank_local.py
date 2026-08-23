"""memory/rerank_local.py — reranker LOCAL cross-encoder (ONNX/CPU) (V2-030 · Fase 2).

Retador autosuficiente del techo OpenAI: un **cross-encoder** `bge-reranker` servido por **fastembed**
(ONNX-Runtime, **CPU** → cero contención con la GPU Apple, que ya cargan STT+TTS). A diferencia del embedding
bi-encoder (vectores independientes), el cross-encoder LEE query+recuerdo JUNTOS y emite un score de relevancia
por par → mucho mejor ordenación a escala. Off-hot-path (solo recall LARGO), carga perezosa, fail-open.

Modelo por defecto `jinaai/jina-reranker-v2-base-multilingual` (multilingüe → bueno en castellano, ~1.1 GB ONNX).
Alternativas ligeras: `BAAI/bge-reranker-base` o `Xenova/ms-marco-MiniLM-L-6-v2` (80 MB, solo-en/latencia).
Configurable por `rerank_model`. Requiere `pip install fastembed` (declarado en requirements.txt).

## The first load is a DOWNLOAD, and nobody may wait for it (2026-08-23)

`TextCrossEncoder(model_name=...)` fetches ~1.1 GB the first time it sees a model, synchronously and with no
timeout of its own. That made the default configuration a trap that only springs on a machine that has never
pulled the model: the first LONG recall of the first real turn blocks on a gigabyte of network, and because
`fastembed` imports fine the status said `available` the whole time. Two things were missing, and neither is
"turn the reranker off":

  - **A clock.** The download is allowed; WAITING for it is not. The load runs in a daemon thread with a
    wall-clock budget: past it, `rank()` returns None and the recall goes out unranked (fail-open, exactly as
    when the provider is absent) while the download keeps going. A later call finds it finished and the
    reranker switches itself on. Nothing is lost but the ordering of the first few long recalls.
  - **Memory of surrender.** `_get()` used to retry from scratch on every call, so a machine that cannot serve
    this model paid the failure again on every single recall. Hard failures are now sticky per model; a TIMEOUT
    is deliberately NOT sticky — it is the one failure that fixes itself.

`ready()` reports whether the model can serve RIGHT NOW, which is what `rerank.status()` publishes so a
measurement can never mistake "downloading" for "reranked" (`scale_eval` reads it)."""
from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger("zaelar.memory.rerank_local")

#: How long a caller may wait for the model to become usable. Generous enough for a warm load from disk
#: (~1-3 s on this hardware), far too short for a 1.1 GB download — which is the point.
LOAD_BUDGET_S = 8.0

_encoder = None
_encoder_model = None
_lock = threading.Lock()
_loading: dict[str, threading.Thread] = {}    # model -> the thread still bringing it in
_result: dict[str, object] = {}               # model -> the encoder, once its thread finished
_gave_up: dict[str, str] = {}                 # model -> reason. STICKY: only for failures that repeat


def _budget() -> float:
    try:
        return float(os.getenv("MEMORY_RERANK_LOAD_BUDGET_S", "") or LOAD_BUDGET_S)
    except ValueError:
        return LOAD_BUDGET_S


def reset() -> None:
    """Drop every cached encoder, thread handle and surrender. For tests and for a config change."""
    global _encoder, _encoder_model
    with _lock:
        _encoder, _encoder_model = None, None
        _loading.clear()
        _result.clear()
        _gave_up.clear()


def _load_into(model: str) -> None:
    """Body of the loader thread: build the encoder, or record why it will never work."""
    try:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        from . import model_cache
        cache = model_cache.models_dir()
        # `cache_dir=None` deja el default de la librería (el TEMP del sistema). Se pasa explícito porque ahí
        # el modelo se PURGA y la descarga vuelve; ver `model_cache.py`.
        enc = TextCrossEncoder(model_name=model, **({"cache_dir": cache} if cache else {}))
    except Exception as e:                     # missing dep, unknown model, corrupt cache, no disk...
        with _lock:
            _gave_up[model] = f"{type(e).__name__}: {e}"
        logger.debug("rerank_local: %s no se pudo cargar: %s", model, e)
        return
    with _lock:
        _result[model] = enc


def _get(model: str):
    """The encoder for `model` if it is usable WITHIN the budget, else None (fail-open).

    Returning None never means "this model is broken" — it can equally mean "still coming". The distinction is
    kept in `_gave_up` so only the first meaning stops us from trying again."""
    global _encoder, _encoder_model
    with _lock:
        if _encoder is not None and _encoder_model == model:
            return _encoder
        if model in _gave_up:
            return None
        enc = _result.pop(model, None)
        if enc is not None:                    # a previous call's thread finished in the meantime
            _encoder, _encoder_model = enc, model
            _loading.pop(model, None)
            return enc
        t = _loading.get(model)
        if t is None:
            t = threading.Thread(target=_load_into, args=(model,), name=f"rerank-load:{model}", daemon=True)
            _loading[model] = t
            t.start()

    t.join(_budget())                          # OUTSIDE the lock: a slow download must not block other callers

    with _lock:
        if t.is_alive():                       # still downloading — not a failure, just not now
            logger.debug("rerank_local: %s aún cargando, este recall sale sin reordenar", model)
            return None
        _loading.pop(model, None)
        if _encoder is not None and _encoder_model == model:
            return _encoder                    # a CONCURRENT caller already claimed this thread's encoder:
                                               # `_result` is popped once, and reading its absence as failure
                                               # would write off a model that is loaded and serving.
        if model in _gave_up:
            return None
        enc = _result.pop(model, None)
        if enc is None:                        # finished without encoder and without reason: refuse to loop
            _gave_up[model] = "el hilo de carga terminó sin encoder"
            return None
        _encoder, _encoder_model = enc, model
        return enc


def ready(model: str | None = None) -> bool:
    """Whether the reranker can serve a query RIGHT NOW — model in memory, no download pending.

    Deliberately NOT the same question as "is fastembed installed": that one is answered by an import and was
    reported as `available` while every recall silently went out unranked."""
    mdl = model or "jinaai/jina-reranker-v2-base-multilingual"
    with _lock:
        return _encoder is not None and _encoder_model == mdl


def loading(model: str | None = None) -> bool:
    """Whether a load (most likely the first download) is in flight for this model."""
    mdl = model or "jinaai/jina-reranker-v2-base-multilingual"
    with _lock:
        t = _loading.get(mdl)
        return bool(t and t.is_alive())


def gave_up(model: str | None = None) -> str | None:
    """Why this model was written off, if it was. None while it is merely slow."""
    mdl = model or "jinaai/jina-reranker-v2-base-multilingual"
    with _lock:
        return _gave_up.get(mdl)


def rank(query: str, texts: list[str], model: str | None = None) -> list[tuple[int, float]] | None:
    """`[(index, score)]` best→worst, keeping the cross-encoder's OWN score per pair. None if unavailable.

    The score is what makes this different from `order()`, and it is the only ABSOLUTE relevance signal anywhere
    in the read path (V2-114 F4.5). Everything else the retriever has is relative: RRF is normalized by the
    fusion's own maximum, so the best of a bad lot always scores ~1; BM25 is not comparable across queries. A
    cross-encoder reads query+document TOGETHER and answers "does THIS text answer THIS question", independent of
    what else was retrieved — which is what a relevance FLOOR needs and a permutation can never provide.

    Raw logits, NOT probabilities (`jina-reranker-v2`, measured 2026-08-18): a real answer lands around -0.7/-1.7
    and unrelated text around -2.8/-3.7. Callers must treat the scale as the model's, never as a probability."""
    if not texts:
        return None
    mdl = model or "jinaai/jina-reranker-v2-base-multilingual"
    enc = _get(mdl)
    if enc is None:
        return None
    try:
        scores = list(enc.rerank(query, texts))   # un score por documento
    except Exception as e:
        logger.debug("rerank_local: rerank falló: %s", e)
        return None
    if not scores or len(scores) != len(texts):
        return None
    idx = sorted(range(len(texts)), key=lambda i: scores[i], reverse=True)
    return [(i, float(scores[i])) for i in idx]


def order(query: str, texts: list[str], model: str | None = None) -> list[int] | None:
    """Devuelve los índices de `texts` ordenados por relevancia a `query` (mejor→peor). None si no disponible."""
    ranked = rank(query, texts, model)
    return None if ranked is None else [i for i, _ in ranked]
