"""nucleo/agentes/otros.py — ⚠️ DEAD COMPONENT (parked in V2-036, 2026-07-13). NOT wired in.

REPLACED by `nucleo/agentes/worker.py` (generic worker driven by Claude Code with memory access +
reporte de progreso, bajo el pool). Se conserva SIN borrar para poder revertir si hiciera falta; el dispatcher ya
It is NOT called (`nucleo/dispatch.py` routes the generic path to `worker`). Decide later whether to remove it.

--- original documentation (historical) ---
GENERIC on-demand work agent for SlowBrain (V2-007 · T86).

Default case: mathematics, one-off search/query, writing, reasoning — anything that is not
driving the browser (`web.py`) or touching widgets/code (`code.py`). It composes the agent's minimum
MEMORY ★, builds the prompt, and runs the config-selected `CodeAgent` with the **PER-INVOCATION model** for the
task type and the trust-based tool policy (`deny_tools` for UNTRUSTED input). Returns a `WorkResult` that
el dispatcher entrega por voz+UI+[SISTEMA] y guarda en memoria.

This is the promotion to its own module of the generic body formerly inline in `dispatch.dispatch()` (V2-006):
the dispatcher becomes a ROUTER (web/code/others), and this component is the generic branch.
"""
from __future__ import annotations

from loguru import logger

from .base import RunSpec, WorkResult


async def run(task) -> WorkResult:
    """Resolves a generic task with the `CodeAgent` (memory → prompt → agent). Never raises."""
    from nucleo import agentes, dispatch, memory_agent

    req = (task.request or "").strip()
    if not req:
        return WorkResult(ok=True, summary="", deliver=False)

    # 1) Minimum context from the memory agent (best effort).
    try:
        context = await memory_agent.compose_context(req, budget=int(task.context.get("budget", 2000)))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"otros: compose_context failed ({e}); continuing without context")
        context = ""

    # 2) Dynamic prompt = context + task.
    prompt = dispatch._build_prompt(req, context, task)

    # 3) Configured agent + PER-INVOCATION model + trust-based tool policy.
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
