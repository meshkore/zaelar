"""nucleo/agentes/web.py — ⚠️ PIEZA MUERTA (parkeada en V2-036 F3, 2026-07-13). Ya NO está cableada.

REEMPLAZADA por `nucleo/agentes/web_cc.py` (un agente Claude Code conduce el navegador vía el puente `hbweb`, con
su propia inteligencia, en vez del `_plan` + bucle barato). El dispatcher enruta `kind=="web"` a `web_cc`.
Se conserva SIN borrar (revertible) — y `web_cc` aún IMPORTA de aquí el helper `_synthesize_goal`. Decidir más
adelante si se elimina. El bucle barato que ejecutaba (`widgets/navegador/agent.py::run_task`) queda igualmente
muerto por este cambio (ya no lo invoca el flujo web; solo lo tocaría el antiguo `automate` del owner, sin caller).

--- doc original (histórica) ---
agente de trabajo WEB del SlowBrain (V2-007 · T84).

Conduce una tarea de navegador (widget `navegador`/Chromium). **Absorbe la orquestación** que en el cerebro viejo
vivía en `duo._orchestrate_automation`: dedup de refinamientos del STT → crear la TAREA y abrir SU tarjeta →
PLANIFICAR el objetivo → encolar la acción `automate` al owner del navegador.

La única diferencia con el flujo viejo es QUIÉN planifica: antes Hermes (`_hermes_ask`), ahora el **SlowBrain**
(un `CodeAgent` barato, modelo por invocación de config `code_agent.model_web`). El **bucle barato DOM→visión**
(`widgets/navegador/agent.py` + `owner.py`) se conserva intacto — sigue EJECUTANDO y sigue REPORTANDO el
resultado real por `proactive`+`[SISTEMA]` cuando termina. Por eso este agente devuelve `deliver=False`: la tarea
es async y su tarjeta/owner entrega el desenlace; aquí solo confirmamos que arrancó.

El confirm-gate de acciones irreversibles NO se aplica al OBJETIVO (un "buscar y comprar" debe poder empezar a
navegar): lo aplica el owner por-acción, justo antes del clic de compra/pago (`owner.py::_DANGER_RE`). Ver `danger.py`.
"""
from __future__ import annotations

import asyncio

from loguru import logger

from .base import RunSpec, WorkResult


def _emit(*a, **k):
    try:
        from voice.observer import emit
        emit(*a, **k)
    except Exception:
        pass


async def _plan(goal: str, task) -> str:
    """PLAN breve y accionable para el objetivo, producido por el SlowBrain (CodeAgent barato, sin tools).
    Best-effort y acotado: si no hay agente/credencial o falla, se sigue sin plan (el bucle DOM→visión no lo
    necesita para arrancar). Modelo POR INVOCACIÓN (`code_agent.model_web`)."""
    from nucleo import agentes, dispatch
    try:
        from voice.engine.core import langs
        native = langs.current_language().native
    except Exception:
        native = "español"
    plan_prompt = (
        "[PLANIFICACIÓN — NO EJECUTAR NADA, NO USAR HERRAMIENTAS] Un agente de navegador realizará esta tarea por "
        f"sí solo, conduciendo una pestaña web NUEVA paso a paso:\n«{goal}»\n"
        f"Da un PLAN BREVE y accionable en {native} (texto plano, 3-6 líneas, sin markdown). Reglas del plan:\n"
        "0) ENTIENDE la búsqueda ANTES de teclear: identifica el SUJETO y su CATEGORÍA EXACTA. Las categorías son "
        "EXCLUYENTES — no las confundas ni las generalices. Ej.: una moto de ENDURO no es de trial, ni de cross, ni "
        "de carretera/naked; un piso no es un local; un portátil gamer no es una tablet. Escribe en el plan la "
        "categoría exacta y qué NO cuenta, para no traer resultados de la categoría equivocada.\n"
        "1) DEPURA el término de búsqueda con TODAS las restricciones del objetivo (tipo/categoría EXACTA, palabras "
        "clave, rango de precio) — no busques un término genérico que devuelva la categoría equivocada.\n"
        "2) Si es una búsqueda en un MARKETPLACE/tienda, la PRIMERA LÍNEA del plan debe ser EXACTAMENTE "
        "`URL: <url de la página de RESULTADOS con los filtros ya puestos>` — keywords DEPURADAS + precio máximo + "
        "orden. Ejemplo: `URL: https://es.wallapop.com/search?keywords=moto+enduro+300&max_sale_price=6000&order_by=most_relevance`. "
        "Así el navegador empieza YA en la rejilla de resultados en vez de teclear en la caja y navegar a mano "
        "(mucho más fiable y rápido). Si no aplica, no pongas la línea URL.\n"
        "3) LOCAL vs AMPLIO: si el objetivo implica cercanía ('cerca de mí', recogida en mano, una ciudad) aplica "
        "filtro de UBICACIÓN u orden por distancia; si no, búsqueda amplia. Dilo explícitamente en el plan.\n"
        "4) Al final, abrir las fichas más prometedoras para extraer precio/estado/ubicación reales.\n"
        "SOLO el plan, sin dirigirte al operador."
    )
    try:
        agent = agentes.get_agent()
        spec = RunSpec(model=dispatch._model_for("web"), tools=[], deny_tools=False, timeout=45.0)
        res = await agent.run(plan_prompt, spec=spec)
        if res.ok and (res.output or "").strip():
            return res.output.strip()[:1200]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"web: planificación falló (sigo sin plan): {e}")
    return ""


async def _synthesize_goal(goal: str) -> str:
    """ESENCIA del objetivo para MOSTRAR en la tarjeta: objetivo + criterios en UNA línea (≤140 car), sin el
    volcado en primera persona. Modelo RÁPIDO/barato (FastClient), off-hot-path, best-effort. Una petición puede
    ser larga y con criterios ('...cerca de donde vive Ricardo. Necesito anuncios activos, modelos populares...') →
    se destila a «Moto de enduro para principiante · Wallapop · cerca · precio razonable». El `goal` operativo
    completo NO se toca (sigue guiando la búsqueda)."""
    goal = (goal or "").strip()
    if not goal:
        return ""
    from nucleo.flash.fast_client import FastClient, spec_from_config
    try:
        from voice.engine.core import langs
        native = langs.current_language().native
    except Exception:
        native = "español"
    prompt = (
        f"Comprime esta petición de búsqueda en su ESENCIA, en UNA sola línea de ≤140 caracteres, en {native}. "
        "Formato «Objetivo · criterio · criterio». CONSERVA todas las restricciones clave (tipo/categoría EXACTA "
        "—no la generalices—, rango de precio, ubicación, sitio/marketplace) y ELIMINA el relleno en primera "
        "persona ('necesito', 'quiero', 'me gustaría'), los nombres propios del operador y las cortesías. No "
        "añadas nada que no esté en la petición. Devuelve SOLO la línea, sin comillas ni prefijos.\n\n"
        f"Petición: «{goal}»"
    )
    try:
        parts: list[str] = []
        async for chunk in FastClient().stream(
                [{"role": "user", "content": prompt}], spec=spec_from_config(), max_tokens=90):
            parts.append(chunk)
        line = " ".join("".join(parts).split()).strip().strip('"').strip("«»")
        return line[:180]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"web: síntesis del goal falló (sigo con el crudo): {e}")
        return ""


async def run(task) -> WorkResult:
    """Orquesta una tarea de navegador. Async/off-voz. Nunca lanza. `deliver=False`: el owner reporta el
    resultado real al terminar (mismo circuito proactive+[SISTEMA] de siempre)."""
    from widgets.navegador import tasks as navtasks

    goal = (task.request or "").strip()
    if not goal:
        return WorkResult(ok=False, error="objetivo vacío", deliver=False)

    # (0-bis) TAREA NUEVA FORZADA (V2-035, 2026-07-13): si el operador pide EXPLÍCITAMENTE otra/segunda/nueva
    # ventana/pestaña/búsqueda EN PARALELO ("abre OTRO navegador…", "en una pestaña NUEVA…", "sin parar la de X,
    # busca Y"), NO se continúa la tarea previa — se crea una tarea/pestaña aparte. Arregla el bug 2026-07-13 en que
    # "cara de perro sin parar la tarea de motos" se fusionó con la búsqueda de motos (t1).
    import re as _re
    _force_new = bool(_re.search(
        r"\b(otro|otra|segundo|segunda|nuevo|nueva|aparte|adem[aá]s|en paralelo|a la vez|otra vez en)\b"
        r"[^.]*\b(navegador|pesta[ñn]a|ventana|b[uú]squeda|tarea)\b", goal, _re.I)) or bool(_re.search(
        r"\bsin (parar|detener|cerrar|tocar)\b", goal, _re.I))

    # (0) CONTINUIDAD (control de estado, 2026-07-12): una MISMA búsqueda NUNCA abre un segundo navegador. Las
    # ACLARACIONES del operador ("no, enduro", "sube el precio") MODIFICAN la tarea que ya está en curso —o la
    # recién terminada— en su MISMA tarjeta, en vez de spawnear un gemelo. Dos temas distintos (moto vs piso) no
    # se fusionan. Ver navtasks.find_continuation.
    try:
        cont = None if _force_new else navtasks.find_continuation(goal)
    except Exception:
        cont = None
    if _force_new:
        _emit("brain", "🆕 tarea NUEVA forzada (el operador pidió otra ventana/pestaña en paralelo)",
              text=goal[:100], role="system")
    if cont:
        tid, status = cont
        try:
            navtasks.set_goal(tid, goal)   # la aclaración MANDA (el FlashBrain envía la petición ya autocontenida)
        except Exception:
            pass
        _emit("widget", "show", extra={"id": navtasks.inst_id(tid)})
        if status in ("queued", "working", "needs_input"):
            # ACTIVA → se refina EN MARCHA: el bucle re-lee el objetivo actualizado en el siguiente paso.
            try:
                navtasks.milestone(tid, f"🔁 ajusto la búsqueda en marcha: {goal[:100]}")
            except Exception:
                pass
            _emit("brain", "🔁 aclaración → tarea en curso modificada (no abro otro navegador)",
                  text=f"{tid}: {goal}", role="system", extra={"id": navtasks.inst_id(tid)})
            return WorkResult(ok=True, summary=f"Ajusto la búsqueda que ya tenía en marcha ({goal[:60]}).",
                              deliver=False, meta={"task_id": tid, "refined": True})
        # TERMINADA hace poco → RE-LANZA en la MISMA tarjeta con el objetivo afinado (no una tarjeta nueva).
        try:
            navtasks.milestone(tid, f"🔁 retomo esta búsqueda con tus aclaraciones: {goal[:100]}")
        except Exception:
            pass
        _emit("brain", "🔁 aclaración → re-lanzo la MISMA tarea (misma tarjeta)", text=f"{tid}: {goal}",
              role="system", extra={"id": navtasks.inst_id(tid)})
        plan, summary = await asyncio.gather(_plan(goal, task), _synthesize_goal(goal))
        if summary:
            try:
                navtasks.set_goal_summary(tid, summary)
            except Exception:
                pass
        try:
            from widgets.server_api import brain_action
            await brain_action("navegador", "automate", {"goal": goal, "plan": plan, "task_id": tid})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"web: no pude re-lanzar la tarea {tid}: {e}")
        return WorkResult(ok=True, summary=f"Retomo la búsqueda con tus aclaraciones ({goal[:60]}).",
                          deliver=False, meta={"task_id": tid, "rerun": True})

    # (1) crea la TAREA y abre su tarjeta YA (una tarjeta arrastrable por tarea; varias en paralelo).
    task_id = navtasks.create(goal)
    inst = navtasks.inst_id(task_id)
    _emit("widget", "show", extra={"id": inst})
    _emit("brain", "🤖 tarea de navegador creada (SlowBrain)", text=f"{task_id}: {goal}", role="system",
          extra={"id": inst})

    # (2) el SlowBrain PLANIFICA (best-effort, no bloquea; la tarea empieza en una pestaña en blanco).
    try:
        navtasks.add_event(task_id, "🧭 planificando…")
    except Exception:
        pass
    plan, summary = await asyncio.gather(_plan(goal, task), _synthesize_goal(goal))
    if summary:
        try:
            navtasks.set_goal_summary(task_id, summary)   # la tarjeta muestra la ESENCIA, no el crudo
        except Exception:
            pass
    try:
        navtasks.add_event(task_id, "📋 plan listo" if plan else "▶️ sin plan, arranco igual")
    except Exception:
        pass

    # (3) ejecuta en la PESTAÑA de esta tarea (owner mailbox → bucle DOM→visión conservado).
    try:
        from widgets.server_api import brain_action
        await brain_action("navegador", "automate", {"goal": goal, "plan": plan, "task_id": task_id})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"web: no pude arrancar la automatización: {e}")
        try:
            navtasks.finish(task_id, "failed", "No pude arrancar la automatización.")
        except Exception:
            pass
        return WorkResult(ok=False, error=str(e), deliver=True,
                          summary="No pude arrancar la tarea de navegador.")

    return WorkResult(ok=True, summary=f"Tarea de navegador en marcha: {goal[:80]}.",
                      deliver=False, meta={"task_id": task_id})
