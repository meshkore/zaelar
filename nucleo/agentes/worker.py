"""nucleo/agentes/worker.py — WORKER genérico conducido por Claude Code (V2-036).

Sustituye a `nucleo/agentes/otros.py` (parkeado): el caso por defecto (razonamiento, redacción, consulta, informe —
todo lo que no sea navegar ni tocar código de widget) lo conduce un agente Claude Code headless que ACTÚA COMO UN
SLOW BRAIN para SU tarea. A diferencia del viejo `otros.py`, este worker:

  • USA la MEMORIA de zaelar EN CURSO como pieza serial: `mem_cli recall` para pedir un dato, `mem_cli remember`
    para guardar lo que descubra — sin abrir la BD (habla por HTTP con el server vivo, escritor único intacto).
  • REPORTA su progreso al FlashBrain con `agent_report phase` → el operador ve la fase de la sesión mientras trabaja
    (las sesiones son lentas; la comunicación constante es lo que las hace usables).

Corre bajo el POOL del dispatcher (concurrencia acotada) y devuelve un `WorkResult` que el dispatcher entrega por
voz+UI+[SISTEMA] y guarda en memoria. El id de sesión viaja por `ZAELAR_TASK_ID` (env) → los CLIs lo toman solos.
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
    """Resuelve una tarea genérica con un agente Claude Code que usa memoria + reporta progreso. Nunca lanza."""
    from nucleo import agentes, dispatch, memory_agent

    req = (task.request or "").strip()
    if not req:
        return WorkResult(ok=True, summary="", deliver=False)

    # 1) contexto mínimo desde el agente de memoria (semilla; el agente puede pedir MÁS con mem_cli recall).
    try:
        context = await memory_agent.compose_context(req, budget=int(task.context.get("budget", 2000)))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"worker: compose_context falló ({e}); sigo sin contexto")
        context = ""

    # 2) prompt = contexto + tarea + doc de herramientas (memoria/reporte).
    prompt = dispatch._build_prompt(req, context, task) + (_TOOLS_DOC if task.trusted else "")

    try:
        dispatch.session_phase(task.id, "pensando")
    except Exception:
        pass

    # 3) agente Claude Code, modelo POR INVOCACIÓN, tools por confianza + el id de sesión por env (para los CLIs).
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
