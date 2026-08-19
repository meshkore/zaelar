"""nucleo/agentes/web_cc.py — WORKER WEB conducido por Claude Code (V2-036 F3).

SUSTITUYE a `nucleo/agentes/web.py` + al bucle barato DOM→visión de `widgets/navegador/agent.py`. Ahora un
agente Claude Code headless CONDUCE el navegador de zaelar paso a paso con SU inteligencia: pide el snapshot, razona
sobre la categoría EXACTA (enduro≠trial≠carretera), navega/clica/escribe/filtra, y extrae los resultados que de
verdad encajan. Dirige el Chromium por el puente `hbweb` (`nucleo/nav_cli` → `POST /api/navegador/act` → el
`TaskBrowser` del owner). Reporta su fase con `hbnote` y usa la memoria con `hbmem`. Corre bajo el POOL del
dispatcher. Una tarea = una pestaña = una tarjeta (continuidad V2-032 conservada: las aclaraciones re-lanzan en la
MISMA tarjeta; "otro/segundo navegador" fuerza una nueva).
"""
from __future__ import annotations

import asyncio
import re

from loguru import logger

from .base import RunSpec, WorkResult


def _emit(*a, **k):
    try:
        from voice.observer import emit
        emit(*a, **k)
    except Exception:
        pass


_PY = ".venv/bin/python"

_FORCE_NEW_RE = re.compile(
    r"\b(otro|otra|segundo|segunda|nuevo|nueva|aparte|adem[aá]s|en paralelo|a la vez)\b[^.]*"
    r"\b(navegador|pesta[ñn]a|ventana|b[uú]squeda|tarea)\b", re.I)
_COEXIST_RE = re.compile(r"\bsin (parar|detener|cerrar|tocar)\b", re.I)


def _web_prompt(goal: str, native: str) -> str:
    from nucleo.flash import site_catalog
    return (
        "Eres un agente que CONDUCE un navegador web REAL de zaelar para cumplir un OBJETIVO del operador, paso a "
        f"paso y con criterio. OBJETIVO (respétalo al pie de la letra):\n«{goal}»\n\n"
        f"{site_catalog.directive_block()}\n\n"
        "CÓMO CONDUCIR (desde la raíz del repo; el navegador ya tiene su pestaña asignada):\n"
        f"• Ver la página y sus elementos:   {_PY} -m nucleo.nav_cli snapshot\n"
        f"• Ir a una URL:                    {_PY} -m nucleo.nav_cli navigate \"<url>\"\n"
        f"• Escribir en un campo [ref]:      {_PY} -m nucleo.nav_cli type <ref> \"<texto>\" --submit\n"
        f"• Clicar un elemento [ref]:        {_PY} -m nucleo.nav_cli click <ref>\n"
        f"• Desplazar / extraer:             {_PY} -m nucleo.nav_cli scroll 800   ·   {_PY} -m nucleo.nav_cli extract\n"
        f"• Reportar tu fase (el operador la VE):   {_PY} -m nucleo.agent_report phase \"<qué haces>\"\n"
        f"• Consultar memoria del operador si hace falta:   {_PY} -m nucleo.mem_cli recall \"<consulta>\"\n\n"
        "REGLAS:\n"
        "1) Las refs [n] son las del ÚLTIMO snapshot → pide snapshot antes de clicar/escribir.\n"
        "2) CATEGORÍA EXACTA: las categorías son EXCLUYENTES. Si el objetivo dice ENDURO, NO es trial, ni cross, ni "
        "carretera/naked; si dice piso, no un local. DEPURA el término y, en marketplaces, usa la URL de RESULTADOS "
        "con filtros (categoría, keywords depuradas, precio máx, orden) en vez de teclear a ciegas.\n"
        "3) LOCAL vs AMPLIO: si el objetivo implica cercanía, aplica ubicación/orden por distancia; si no, amplio.\n"
        "4) Verifica MIENTRAS avanzas que lo que ves sigue el objetivo; si la página muestra otra categoría, corrige "
        "el término en vez de seguir. NO abras el mismo anuncio en bucle.\n"
        "5) Al final: `extract` para sacar los anuncios reales, DESCARTA los que no encajan (di por qué), y escribe "
        f"tu conclusión para el operador en {native}, natural y humana, con los 2-3 que MEJOR encajan (título, "
        "precio, por qué). Reporta fase al empezar y al cambiar de etapa.\n"
        "Tu ÚLTIMA salida de texto es lo que se le DIRÁ al operador. No inventes resultados; básate en lo que viste."
    )


async def run(task) -> WorkResult:
    """Conduce una tarea de navegador con un agente Claude Code. Async/off-voz, bajo el pool. Nunca lanza."""
    from widgets.navegador import tasks as navtasks
    from nucleo import agentes, dispatch

    goal = (task.request or "").strip()
    if not goal:
        return WorkResult(ok=False, error="objetivo vacío", deliver=False)

    force_new = bool(_FORCE_NEW_RE.search(goal)) or bool(_COEXIST_RE.search(goal))
    try:
        cont = None if force_new else navtasks.find_continuation(goal)
    except Exception:
        cont = None

    if cont:
        tid = cont[0]
        try:
            navtasks.set_goal(tid, goal)
        except Exception:
            pass
        _emit("brain", "🔁 aclaración → re-conduzco la MISMA tarea (misma tarjeta)", text=f"{tid}: {goal}",
              role="system", extra={"id": navtasks.inst_id(tid)})
    else:
        tid = navtasks.create(goal)
        _emit("brain", "🤖 tarea de navegador (Claude Code)", text=f"{tid}: {goal}", role="system",
              extra={"id": navtasks.inst_id(tid)})
    inst = navtasks.inst_id(tid)
    _emit("widget", "show", extra={"id": inst, "src": f"worker:{tid}"})

    # ESENCIA del objetivo en la tarjeta (reutiliza el sintetizador; best-effort).
    try:
        from nucleo.agentes.web import _synthesize_goal
        summary = await _synthesize_goal(goal)
        if summary:
            navtasks.set_goal_summary(tid, summary)
    except Exception:
        pass
    try:
        navtasks.set_status(tid, "working")
        navtasks.set_phase(tid, "conduciendo el navegador", True)
    except Exception:
        pass

    # AGENTE Claude Code que conduce el navegador (hbweb) + memoria (hbmem) + reporte (hbnote). tools=[] → el
    # adaptador añade SOLO las tools-puente (V2-036), no Bash abierto. env: id de escalada (hbnote) + id de navtask
    # (hbweb, para que las capturas casen con la tarjeta).
    try:
        from voice.engine.core import langs
        native = langs.current_language().native
    except Exception:
        native = "español"
    agent = agentes.get_agent()
    spec = RunSpec(
        model=dispatch._model_for("web"),
        tools=[] if task.trusted else None,
        deny_tools=not task.trusted,
        timeout=float(task.context.get("timeout", 600.0)),
        env={"ZAELAR_TASK_ID": str(task.id), "ZAELAR_NAV_TASK": str(tid)},
    )
    logger.info(f"web_cc: tarea {task.id} (navtask {tid}) → Claude Code conduce el navegador")
    result = await agent.run(_web_prompt(goal, native), spec=spec)

    # RESULTADOS en la tarjeta: extrae lo que quedó en pantalla (best-effort) para pintar los anuncios.
    try:
        from widgets.navegador import owner
        tb = owner._task_browsers.get(str(tid))
        if tb is not None:
            items = await tb.extract_listings()
            if items:
                navtasks.set_results(tid, {"conclusion": (result.output or "").strip()[:300], "items": items[:5]})
    except Exception:
        pass

    ok = bool(result.ok and (result.output or "").strip())
    try:
        navtasks.finish(tid, "done" if ok else "failed",
                        ("✅ " if ok else "") + ((result.output or "").strip()[:200] or "sin resultado"))
    except Exception:
        pass
    if ok:
        return WorkResult(ok=True, summary=result.output.strip(), deliver=True, meta={"task_id": tid})
    return WorkResult(ok=False, error=result.error or "sin salida",
                      summary="No pude completar la búsqueda en el navegador.", deliver=True, meta={"task_id": tid})
