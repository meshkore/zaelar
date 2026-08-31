"""tests/memory/judge/judge.py — TEMPORAL memory-correction judge (V2-105, 2026-08-17).

Neither `tests/memory/e2e/bot/` nor `tests/memory/e2e/timeline/` has this piece: their checks are deterministic
SUBSTRING checks (`marker in text`) — they match TEXT, never asking whether the retrieved FACT is still the
current one. This is the kind of failure that the longitudinal corpus (V2-105) was built to detect
(delayed contradiction, paraphrase, competing fact): a response may contain the correct text marker and still
be OBSOLETE, or vice versa.

Pattern adapted from `tests/voice/e2e/agent/judge/judge.py` (same spirit — independent evaluator, closed JSON,
actionable verdict) but for the MEMORY seam (`nucleo/memllm.py`, not the voice tester's): memory and voice are
separate subsystems with their own model catalogs (`zaelar-modularity.md`).

REAL cost per invocation (operator policy, 2026-08-17: "all validations have to be real... we do not care
about the cost") — used on demand/for calibration, NEVER in the fast pytest run for each commit (same pattern
as `distiller_bench.py`/`scale_eval.py`).
"""
from __future__ import annotations

import json

from loguru import logger

from nucleo import memllm

VERDICTS = ("correct", "stale", "wrong", "absent")

_SYSTEM = (
    "Juzgas si la memoria de un asistente personal sigue siendo CORRECTA en un punto concreto del tiempo. Te "
    "doy una PREGUNTA, lo que el RETRIEVER devolvió de verdad, y el HECHO VIGENTE que el propio guion de "
    "prueba conoce por construcción (la verdad de terreno). Clasifica en UNO de cuatro veredictos:\n"
    "- correct: lo recuperado refleja el hecho VIGENTE, aunque esté dicho con otras palabras.\n"
    "- stale: lo recuperado fue cierto en su día pero YA NO es el hecho vigente (una versión superada).\n"
    "- wrong: lo recuperado contradice el hecho vigente y NUNCA fue correcto (fabricación, mezcla, error).\n"
    "- absent: no hay nada relevante en lo recuperado — la pregunta queda sin responder.\n"
    "No premies una coincidencia de PALABRAS si el HECHO ya cambió; no penalices una respuesta correcta solo "
    "porque use vocabulario distinto al de la pregunta. Responde SOLO JSON, sin explicación fuera del JSON."
)

_SCHEMA = (
    '{"veredicto": "correct|stale|wrong|absent", "razon": "una frase, en qué te basas", '
    '"cita": "el fragmento concreto de lo recuperado que sustenta el veredicto, o \\"\\" si absent"}'
)


def judge_recall(question: str, retrieved: str, ground_truth: str, *, model_override: str | None = None,
                 url_override: str | None = None) -> dict:
    """REAL judgment (call to DeepSeek via `nucleo/memllm.chat_sync`, task `"rem"` — same cost profile as
    the rest of memory's off-hot-path tasks). Structured fail-open: if the model does not respond or the
    response cannot be parsed, verdict `"absent"` with `_error` — the calibrator run never crashes."""
    user = json.dumps({
        "pregunta": question,
        "recuperado_por_el_retriever": retrieved or "(nada — el retriever no devolvió resultados)",
        "hecho_vigente_segun_el_guion": ground_truth,
    }, ensure_ascii=False, indent=1)
    content = memllm.chat_sync("rem", _SYSTEM + "\n\nFormato:\n" + _SCHEMA, user, max_tokens=300, timeout=60.0,
                               model_override=model_override, url_override=url_override)
    if not content:
        return {"veredicto": "absent", "razon": "el juez no respondió", "cita": "", "_error": "no_content"}
    try:
        start, end = content.find("{"), content.rfind("}")
        v = json.loads(content[start:end + 1])
        if v.get("veredicto") not in VERDICTS:
            raise ValueError(f"veredicto fuera de catálogo: {v.get('veredicto')!r}")
        return v
    except Exception as e:  # noqa: BLE001
        logger.warning(f"judge_recall: respuesta no parseable: {str(e)[:120]}")
        return {"veredicto": "absent", "razon": f"respuesta no parseable: {e}", "cita": "",
                "_error": "unparseable", "_raw": content[:300]}
