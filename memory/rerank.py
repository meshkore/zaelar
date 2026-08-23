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
    """What the reranker IS doing, not merely what it could do.

    `available` answers "is this provider wired up at all"; it says nothing about whether a query gets reranked.
    On the local provider those two drifted apart badly (2026-08-23): `import fastembed` succeeds on a machine
    that has never pulled the 1.1 GB model, so `available` read True while every recall went out unranked and
    a measurement reading this dict would have credited the reranker for the retriever's own ordering.
    `ready`/`loading` are the ones that answer the real question. `None` on a provider that cannot report them
    means no verdict — never False."""
    p = provider()
    st = {"provider": p, "model": _model() if p != "off" else None,
          "enabled": enabled(), "available": _available(p), "top_n": _top_n(),
          "ready": None, "loading": None, "gave_up": None}
    if p == "local":
        try:
            from . import rerank_local
            mdl = _model()
            st["ready"] = rerank_local.ready(mdl)
            st["loading"] = rerank_local.loading(mdl)
            st["gave_up"] = rerank_local.gave_up(mdl)
        except Exception:
            pass
    return st


def _available(p: str) -> bool:
    if p in ("", "off"):
        return False
    if p == "openai":
        return bool(_api_key())
    if p == "local":
        # The dependency being importable is all this claims. Whether the MODEL can serve is `rerank_local.ready`,
        # published separately in `status()` — see the note there.
        try:
            import fastembed  # noqa: F401
        except Exception:
            return False
        from . import rerank_local
        return rerank_local.gave_up(_model()) is None
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
    # EGRESS (T304). Solo si hay base_url explícita: sin ella el SDK va a OpenAI por defecto y no hay
    # nada que reenrutar — el reranker remoto es opt-in y este camino está dormido por defecto.
    if base_url:
        from nucleo import llm_egress
        base_url, key, _extra = llm_egress.route(base_url, key)
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
        from nucleo import energy_meter as _energy
        _energy.meter_openai_response(resp, base_url=base_url or "", model=_model())
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
    ranked = _rank_local(query, texts)
    return None if ranked is None else [i for i, _ in ranked]


def _rank_local(query: str, texts: list[str]) -> list[tuple[int, float]] | None:
    try:
        from . import rerank_local
    except Exception:
        return None
    return rerank_local.rank(query, texts, _model())


# Provider -> the NAME of the function that serves it, resolved LATE (`_impl`). Holding the function objects
# directly used to capture them at import time, so replacing `_order_local` on this module — which is how both a
# test and an in-place hotfix would do it — left these tables pointing at the original and the substitution was
# invisible with no error anywhere. The names are the indirection; the tables are just routing.
_ORDERERS = {"openai": "_order_openai", "local": "_order_local"}

# Providers that can ALSO report an absolute per-pair score, not just a permutation (`rr_abs`). The listwise
# `openai` provider deliberately has no entry: an LLM asked to sort indices returns a ranking with no calibrated
# magnitude, and manufacturing one from its position would be exactly the relative-disguised-as-absolute mistake
# an absolute score exists to avoid.
_RANKERS = {"local": "_rank_local"}


def _impl(table: dict[str, str], p: str):
    name = table.get(p)
    return globals().get(name) if name else None


def scores_available() -> bool:
    """Whether the active provider can report absolute per-pair scores (`rr_abs`)."""
    return provider() in _RANKERS


# ── API pública ─────────────────────────────────────────────────────────────────────────────────────────────
def rerank(query: str, candidates: list[dict], top_n: int | None = None) -> list[dict]:
    """Reordena `candidates` (dicts con 'text' y 'score') por relevancia real a `query`. FAIL-OPEN: ante cualquier
    problema devuelve la lista intacta. Solo reordena el tope `top_n`; el resto de la cola se conserva.

    Marca cada candidato reordenado con `rr` (score de rerank normalizado [0,1]) y funde con su `score` original
    (`blend`) para preservar algo de recencia/importancia. Devuelve la lista completa reordenada.

    Also stamps **`rr_abs`** — the cross-encoder's OWN score for this (query, text) pair — when the provider can
    report one (`scores_available()`). `rr` is POSITIONAL, so the best of a bad lot always gets 1.0; `rr_abs` is
    the same quantity the model would give that pair in any other query, which is what lets `retriever.search()`
    ask "is this actually relevant?" rather than only "is this the most relevant of what came back". Absent when
    the provider cannot report it — callers must treat a missing `rr_abs` as no verdict, never as zero."""
    p = provider()
    orderer = _impl(_ORDERERS, p)
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
    ranker = _impl(_RANKERS, p)
    abs_by_idx: dict[int, float] = {}
    try:
        if ranker is not None:
            ranked = ranker(query, texts)
            order = None if ranked is None else [i for i, _ in ranked]
            abs_by_idx = {} if ranked is None else {i: s for i, s in ranked}
        else:
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
    ranked_head = [head[i] for i in order]
    unranked = [head[i] for i in range(len(head)) if i not in rr]
    for pos, c in enumerate(ranked_head):
        rr_s = 1.0 - (pos / max(1, m))
        c["rr"] = round(rr_s, 4)
        c["score"] = blend * rr_s + (1.0 - blend) * (float(c.get("score", 0.0)) / max_score)
        c["via"] = "rerank"
        if order[pos] in abs_by_idx:
            c["rr_abs"] = round(abs_by_idx[order[pos]], 4)
    for c in unranked:
        c["rr"] = 0.0
    # `unranked`/`tail` deliberately get NO `rr_abs`: the cross-encoder never scored them (the listwise provider
    # may omit indices, and `tail` is beyond `top_n`). Stamping a placeholder would let the floor drop rows on a
    # verdict nobody issued — absent means "not judged", which the floor treats as passing.
    return ranked_head + unranked + tail
