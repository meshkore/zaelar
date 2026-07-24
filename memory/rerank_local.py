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


def order(query: str, texts: list[str], model: str | None = None) -> list[int] | None:
    """Devuelve los índices de `texts` ordenados por relevancia a `query` (mejor→peor). None si no disponible."""
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
    return sorted(range(len(texts)), key=lambda i: scores[i], reverse=True)
