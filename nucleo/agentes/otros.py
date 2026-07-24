"""nucleo/agentes/otros.py — ⚠️ PIEZA MUERTA (parkeada en V2-036, 2026-07-13). NO está cableada.

REEMPLAZADA por `nucleo/agentes/worker.py` (worker genérico conducido por Claude Code con acceso a memoria +
reporte de progreso, bajo el pool). Se conserva SIN borrar para poder revertir si hiciera falta; el dispatcher ya
NO la llama (`nucleo/dispatch.py` enruta el genérico a `worker`). Decidir más adelante si se elimina.

--- doc original (histórica) ---
agente de trabajo GENÉRICO on-demand del SlowBrain (V2-007 · T86).

El caso por defecto: matemáticas, búsqueda/consulta puntual, redacción, razonamiento — cualquier cosa que no sea
conducir el navegador (`web.py`) ni tocar widgets/código (`code.py`). Compone el contexto mínimo del agente de
MEMORIA ★, arma el prompt y corre el `CodeAgent` seleccionado por config con el **modelo POR INVOCACIÓN** del tipo
de tarea y la política de tools por confianza (`deny_tools` para input NO confiable). Devuelve un `WorkResult` que
el dispatcher entrega por voz+UI+[SISTEMA] y guarda en memoria.

Es la promoción a módulo propio del cuerpo genérico que vivía inline en `dispatch.dispatch()` (V2-006): el
dispatcher pasa a ser un ROUTER (web/code/otros) y esta pieza es el ramal genérico.
"""
from __future__ import annotations

from loguru import logger

from .base import RunSpec, WorkResult


async def run(task) -> WorkResult:
    """Resuelve una tarea genérica con el `CodeAgent` (memoria → prompt → agente). Nunca lanza."""
    from nucleo import agentes, dispatch, memory_agent

    req = (task.request or "").strip()
    if not req:
        return WorkResult(ok=True, summary="", deliver=False)

    # 1) contexto mínimo desde el agente de memoria (best-effort).
    try:
        context = await memory_agent.compose_context(req, budget=int(task.context.get("budget", 2000)))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"otros: compose_context falló ({e}); sigo sin contexto")
        context = ""

    # 2) prompt dinámico = contexto + tarea.
    prompt = dispatch._build_prompt(req, context, task)

    # 3) agente por config + modelo POR INVOCACIÓN + política de tools por confianza.
    agent = agentes.get_agent()
    spec = RunSpec(
        model=dispatch._model_for(task.kind),
        tools=dispatch._tools_for(task),
        deny_tools=not task.trusted,           # input no confiable → sin herramientas
        timeout=float(task.context.get("timeout", dispatch._DEFAULT_TIMEOUT)),
        cwd=task.context.get("cwd"),
    )
    logger.info(f"otros: tarea {task.id} ({task.kind}, trusted={task.trusted}) → agente {agent.name}")
    result = await agent.run(prompt, spec=spec)

    if result.ok and (result.output or "").strip():
        return WorkResult(ok=True, summary=result.output.strip(), deliver=True)
    return WorkResult(ok=False, error=result.error or "sin salida",
                      summary="", deliver=True)
