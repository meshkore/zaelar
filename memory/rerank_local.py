"""memory/rerank_local.py — reranker LOCAL cross-encoder (ONNX/CPU) (V2-030 · Fase 2).

Retador autosuficiente del techo OpenAI: un **cross-encoder** `bge-reranker` servido por **fastembed**
(ONNX-Runtime, **CPU** → cero contención con la GPU Apple, que ya cargan STT+TTS). A diferencia del embedding
bi-encoder (vectores independientes), el cross-encoder LEE query+recuerdo JUNTOS y emite un score de relevancia
por par → mucho mejor ordenación a escala. Off-hot-path (solo recall LARGO), carga perezosa, fail-open.

Modelo por defecto `jinaai/jina-reranker-v2-base-multilingual` (multilingüe → bueno en castellano, ~1.1 GB ONNX).
Alternativas ligeras: `BAAI/bge-reranker-base` o `Xenova/ms-marco-MiniLM-L-6-v2` (80 MB, solo-en/latencia).
Configurable por `rerank_model`. Requiere `pip install fastembed` (declarado en requirements.txt)."""
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.memory.rerank_local")

_encoder = None
_encoder_model = None


def _get(model: str):
    """Carga (perezosa, cacheada por modelo) el TextCrossEncoder de fastembed. None si fastembed no está."""
    global _encoder, _encoder_model
    if _encoder is not None and _encoder_model == model:
        return _encoder
    try:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
    except Exception:
        return None
    try:
        _encoder = TextCrossEncoder(model_name=model)
        _encoder_model = model
        return _encoder
    except Exception as e:
        logger.debug("rerank_local: no se pudo cargar %s: %s", model, e)
        return None


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
