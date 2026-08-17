"""tests/memory/judge/judge.py — juez de corrección TEMPORAL de la memoria (V2-105, 2026-08-17).

Ni `tests/memory/e2e/bot/` ni `tests/memory/e2e/timeline/` tienen esta pieza: sus comprobaciones son
SUBSTRING determinista (`marker in texto`) — coinciden en TEXTO, nunca preguntan si el HECHO recuperado sigue
siendo el vigente. Es la clase de fallo que el corpus longitudinal (V2-105) fue construido para poder detectar
(contradicción diferida, paráfrasis, hecho en competencia): una respuesta puede contener el marcador de texto
correcto y aun así estar OBSOLETA, o viceversa.

Patrón adaptado de `tests/voice/e2e/agent/judge/judge.py` (mismo espíritu — evaluador independiente, JSON
cerrado, veredicto accionable) pero por la costura de MEMORIA (`nucleo/memllm.py`, no la del tester de voz):
memoria y voz son subsistemas separados con sus propios catálogos de modelo (`zaelar-modularity.md`).

Coste REAL por invocación (norma del operador, 2026-08-17: "todas las validaciones tienen que ser reales... no
nos importa el coste") — se usa a demanda/calibración, NUNCA en el pytest rápido de cada commit (mismo patrón
que `distiller_bench.py`/`scale_eval.py`).
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
    """Juicio REAL (llamada a DeepSeek vía `nucleo/memllm.chat_sync`, task `"rem"` — mismo perfil de coste que
    el resto de tareas off-hot-path de memoria). Fail-open estructurado: si el modelo no responde o la
    respuesta no parsea, veredicto `"absent"` con `_error` — nunca revienta la corrida del calibrador."""
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
