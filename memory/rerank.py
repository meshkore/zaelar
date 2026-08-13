"""memory/rerank.py — RE-RANKING del recall largo, MODEL-AGNOSTIC (V2-030).

El retriever híbrido (`memory/retriever.py`) recupera candidatos por vector (embeddinggemma local) + FTS y los
funde con RRF. A ESCALA (cientos de recuerdos) el embedding local plano ordena "borroso": la respuesta suele estar
en el top-10 pero no en el top-1/3 (medido en `scale_eval`). Un **reranker** vuelve a puntuar cada candidato
LEYENDO query+recuerdo juntos → sube el correcto. Es la mayor palanca de recall por el menor coste.

**Contrato (igual que el routing de modelos del cerebro, `config/v2.py`): proveedor CONFIGURABLE, elegido por la
UI/config, local por defecto, listo para cloud/APIs externas.** Hoy corremos con nuestra GPU/CPU porque la tenemos;
la versión cloud solo cambia `rerank_provider`. Proveedores:

  - `off`      — sin reranker (orden del retriever tal cual). DEFAULT hasta medir.
  - `openai`   — LLM listwise vía la API OpenAI (o cualquier endpoint OpenAI-compatible). Techo de calidad.
  - `local`    — cross-encoder ONNX/CPU (fastembed, `bge-reranker-v2-m3`), autosuficiente, cero GPU. (Fase 2)
  - `cohere` / `voyage` — APIs de rerank dedicadas (slots; se cablean cuando haya key).

**Invariantes:**
  - Solo se usa en la ruta LARGO, **fuera del hot path** (el recall largo ya va bajo demanda + `asyncio.to_thread`).
    ESTADO/CORTO NO se tocan — siguen sin modelo (lectura directa µs, V2-013).
  - **FAIL-OPEN duro**: cualquier error/timeout/ausencia de key → se devuelve el orden de entrada intacto. El
    reranker NUNCA puede romper ni bloquear el recall.
  - El reranker no es GENERATIVO: reordena candidatos ya recuperados, no inventa (no viola "no alucinar").
"""
from __future__ import annotations

import json
import logging
import os
import re

logger = logging.getLogger("zaelar.memory.rerank")

# Cuántos candidatos del tope se reordenan (el resto de la cola conserva su orden). Barato y suficiente: el techo
# de un reranker es lo que el retriever ya trajo (found@10 ≈ 82%).
DEFAULT_TOP_N = 20
# Mezcla rerank↔score original: el rerank DOMINA, pero conservamos algo de recencia/importancia para no perder la
# frescura (un hecho recién dicho no debe hundirse por un match semántico viejo).
DEFAULT_BLEND = 0.85


# ── configuración (store > env, mismo patrón que config/v2.py) ──────────────────────────────────────────────
def _cfg() -> dict:
    try:
        from config import v2 as _v2
        return _v2.get("memory")
    except Exception:
        # sin config/v2 (tests aislados): solo env.
        return {
            "rerank_provider": os.getenv("MEMORY_RERANK", "off"),
            "rerank_model": os.getenv("MEMORY_RERANK_MODEL", ""),
            "rerank_top_n": os.getenv("MEMORY_RERANK_TOP_N", ""),
            "rerank_blend": os.getenv("MEMORY_RERANK_BLEND", ""),
            "rerank_api_key": os.getenv("MEMORY_RERANK_KEY", ""),
        }


def provider() -> str:
    return (str(_cfg().get("rerank_provider") or "off")).strip().lower()


def _model() -> str:
    m = str(_cfg().get("rerank_model") or "").strip()
    if m:
        return m
    return {"openai": "gpt-4o-mini",
            "local": "jinaai/jina-reranker-v2-base-multilingual"}.get(provider(), "")


def _top_n() -> int:
    try:
        return int(_cfg().get("rerank_top_n") or DEFAULT_TOP_N)
    except Exception:
        return DEFAULT_TOP_N


def _blend() -> float:
    try:
        return float(_cfg().get("rerank_blend") or DEFAULT_BLEND)
    except Exception:
        return DEFAULT_BLEND


def _api_key() -> str:
    return (str(_cfg().get("rerank_api_key") or "").strip()
            or os.getenv("MEMORY_RERANK_KEY", "")
            or os.getenv("OPENAI_API_KEY", ""))


def enabled() -> bool:
    return provider() not in ("", "off", "none", "0", "false")


def status() -> dict:
    p = provider()
    return {"provider": p, "model": _model() if p != "off" else None,
            "enabled": enabled(), "available": _available(p), "top_n": _top_n()}


def _available(p: str) -> bool:
    if p in ("", "off"):
        return False
    if p == "openai":
        return bool(_api_key())
    if p == "local":
        try:
            import fastembed  # noqa: F401
            return True
        except Exception:
            return False
    return False


# ── proveedores: cada uno devuelve una permutación (índices de `texts`, mejor→peor). None = no disponible ────
def _order_openai(query: str, texts: list[str]) -> list[int] | None:
    """LLM listwise: el modelo lee query + candidatos numerados y devuelve los índices ordenados por relevancia.
    Cualquier endpoint OpenAI-compatible (base_url configurable). Barato (modelo pequeño), off-hot-path."""
    key = _api_key()
    if not key:
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None
    base_url = str(_cfg().get("rerank_base_url") or "").strip() or None
    cli = OpenAI(api_key=key, base_url=base_url, timeout=float(os.getenv("MEMORY_RERANK_TIMEOUT", "12")))
    listing = "\n".join(f"[{i}] {t[:280]}" for i, t in enumerate(texts))
    sys = ("Eres un reordenador de recuerdos. Dada una PREGUNTA y una lista de RECUERDOS numerados, devuelve SOLO "
           "un array JSON con los índices ordenados del MÁS al MENOS relevante para responder la pregunta. "
           "Incluye únicamente los índices claramente relevantes (puedes omitir los irrelevantes). "
           'Ejemplo de salida: [3, 0, 7]. Nada de texto extra.')
    usr = f"PREGUNTA: {query}\n\nRECUERDOS:\n{listing}"
    try:
        resp = cli.chat.completions.create(
            model=_model(), temperature=0,
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": usr}],
        )
        raw = (resp.choices[0].message.content or "").strip()
        # A ENERGY (2026-08-13). El default del reranker es LOCAL y gratis, así que esta rama estaba
        # dormida y por eso pasó desapercibida — pero es una elección de CONFIG (`rerank_provider`), no
        # una imposibilidad: el día que se ponga en remoto empezaría a costar dinero real sin aparecer en
        # ninguna factura. Se mide ahora, dormida, para que encenderla no sea gratis por descuido.
        try:
            from nucleo import energy_meter as _energy
            u = getattr(resp, "usage", None)
            _energy.report_llm_usage(
                base_url=base_url or "", model=_model(),
                prompt_tokens=getattr(u, "prompt_tokens", None),
                completion_tokens=getattr(u, "completion_tokens", None),
            )
        except Exception:  # noqa: BLE001 — fail-open: el reranker nunca rompe el recall
            pass
    except Exception as e:
        logger.debug("rerank openai falló: %s", e)
        return None
    m = re.search(r"\[[\s\d,]*\]", raw)
    if not m:
        return None
    try:
        idxs = json.loads(m.group(0))
    except Exception:
        return None
    seen, order = set(), []
    for i in idxs:
        if isinstance(i, int) and 0 <= i < len(texts) and i not in seen:
            seen.add(i)
            order.append(i)
    return order or None


def _order_local(query: str, texts: list[str]) -> list[int] | None:
    """Cross-encoder ONNX/CPU (fastembed TextCrossEncoder). Se implementa en Fase 2."""
    try:
        from . import rerank_local
    except Exception:
        return None
    return rerank_local.order(query, texts, _model())


_ORDERERS = {"openai": _order_openai, "local": _order_local}


# ── API pública ─────────────────────────────────────────────────────────────────────────────────────────────
def rerank(query: str, candidates: list[dict], top_n: int | None = None) -> list[dict]:
    """Reordena `candidates` (dicts con 'text' y 'score') por relevancia real a `query`. FAIL-OPEN: ante cualquier
    problema devuelve la lista intacta. Solo reordena el tope `top_n`; el resto de la cola se conserva.

    Marca cada candidato reordenado con `rr` (score de rerank normalizado [0,1]) y funde con su `score` original
    (`blend`) para preservar algo de recencia/importancia. Devuelve la lista completa reordenada."""
    p = provider()
    orderer = _ORDERERS.get(p)
    if not orderer or not candidates:
        return candidates
    n = top_n or _top_n()
    head, tail = candidates[:n], candidates[n:]
    texts = [str(c.get("text", "")) for c in head]
    # FASE 3: marca CONTENCIÓN mientras el cross-encoder reordena (local=CPU/ONNX, poco choque con GPU; aun así lo
    # marcamos para correlacionar con el TTFT del turno). Best-effort.
    _mb = None
    if p == "local":
        try:
            from voice.observer import mark_busy as _mb
        except Exception:
            _mb = None
    if _mb:
        _mb("rerank", True)
    try:
        order = orderer(query, texts)
    except Exception as e:
        logger.debug("rerank %s excepción: %s", p, e)
        return candidates
    finally:
        if _mb:
            _mb("rerank", False)
    if not order:
        return candidates
    # rr_score por posición en la permutación (mejor=1.0). Los no rankeados quedan al final con rr=0.
    m = len(order)
    rr = {idx: 1.0 - (pos / max(1, m)) for pos, idx in enumerate(order)}
    blend = _blend()
    max_score = max((float(c.get("score", 0.0)) for c in head), default=1.0) or 1.0
    ranked = [head[i] for i in order]
    unranked = [head[i] for i in range(len(head)) if i not in rr]
    for pos, c in enumerate(ranked):
        rr_s = 1.0 - (pos / max(1, m))
        c["rr"] = round(rr_s, 4)
        c["score"] = blend * rr_s + (1.0 - blend) * (float(c.get("score", 0.0)) / max_score)
        c["via"] = "rerank"
    for c in unranked:
        c["rr"] = 0.0
    return ranked + unranked + tail
