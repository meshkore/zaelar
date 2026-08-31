"""nucleo/agentes/worker.py — GENERIC WORKER driven by Claude Code (V2-036).

Replaces `nucleo/agentes/otros.py` (parked): the default case (reasoning, writing, queries, reports —
everything that is not browsing or touching widget code) is driven by a headless Claude Code agent that ACTS AS A
SLOW BRAIN para SU tarea. A diferencia del viejo `otros.py`, este worker:

  • USA la MEMORIA de zaelar EN CURSO como pieza serial: `mem_cli recall` para pedir un dato, `mem_cli remember`
    to save what it discovers — without opening the DB (it talks over HTTP to the live server; the single writer remains intact).
  • REPORTS progress to FlashBrain with `agent_report phase` → the operator sees the session phase while it works
    (sessions are slow; constant communication is what makes them usable).

Corre bajo el POOL del dispatcher (concurrencia acotada) y devuelve un `WorkResult` que el dispatcher entrega por
voice+UI+[SYSTEM] and saves to memory. The session ID travels through `ZAELAR_TASK_ID` (env) → the CLIs pick it up automatically.
"""
from __future__ import annotations

from loguru import logger

from .base import RunSpec, WorkResult

_PY = ".venv/bin/python"   # intérprete del venv (cwd del agente = raíz de zaelar)

_TOOLS_DOC = (
    "\n\nHERRAMIENTAS DE zaelar (úsalas desde la raíz del repo; son la forma sancionada, NO abras la BD ni ficheros "
    "de memoria a mano):\n"
    f"• Pedir un dato a la memoria:   {_PY} -m nucleo.mem_cli recall \"<consulta>\"\n"
    f"• Guardar un dato en memoria:   {_PY} -m nucleo.mem_cli remember \"<dato>\" --slot <clave.opcional>\n"
    f"• Reportar tu progreso (que el operador VEA qué haces):   {_PY} -m nucleo.agent_report phase \"<fase actual>\"\n"
    "Reporta la fase al empezar y cuando cambies de etapa. Consulta la memoria si necesitas contexto del operador; "
    "guarda en memoria SOLO lo que valga la pena recordar entre sesiones. Tu ÚLTIMA salida de texto es la respuesta "
    "que se le DIRÁ al operador: escríbela natural y humana, sin jerga interna."
)


async def run(task) -> WorkResult:
    """Resolves a generic task with a Claude Code agent that uses memory and reports progress. Never raises."""
    from nucleo import agentes, dispatch, memory_agent

    req = (task.request or "").strip()
    if not req:
        return WorkResult(ok=True, summary="", deliver=False)

    # 1) Minimum context from the memory agent (seed; the agent can request MORE with mem_cli recall).
    try:
        context = await memory_agent.compose_context(req, budget=int(task.context.get("budget", 2000)))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"worker: compose_context failed ({e}); continuing without context")
        context = ""

    # 2) Prompt = context + task + tool documentation (memory/reporting).
    prompt = dispatch._build_prompt(req, context, task) + (_TOOLS_DOC if task.trusted else "")

    try:
        dispatch.session_phase(task.id, "pensando")
    except Exception:
        pass

    # 3) Claude Code agent, PER-INVOCATION model, trust-based tools + session ID via env (for the CLIs).
    agent = agentes.get_agent()
    spec = RunSpec(
        model=dispatch._model_for(task.kind),
        tools=dispatch._tools_for(task),
        deny_tools=not task.trusted,           # input no confiable → sin herramientas (ni memoria ni reporte)
        timeout=float(task.context.get("timeout", dispatch._DEFAULT_TIMEOUT)),
        cwd=task.context.get("cwd"),
        env={"ZAELAR_TASK_ID": str(task.id)},
    )
    logger.info(f"worker: tarea {task.id} ({task.kind}, trusted={task.trusted}) → agente {agent.name}")
    result = await agent.run(prompt, spec=spec)

    if result.ok and (result.output or "").strip():
        return WorkResult(ok=True, summary=result.output.strip(), deliver=True)
    return WorkResult(ok=False, error=result.error or "sin salida", summary="", deliver=True)
