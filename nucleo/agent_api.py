"""nucleo/agent_api.py — CANAL DE REPORTE de los agentes Claude Code hacia el proceso vivo (V2-036).

Los workers Claude Code son SUBPROCESOS: no comparten el bus/estado in-process del server. Este endpoint es el
puente por HTTP para que reporten su PROGRESO (fase) y datos al FlashBrain/UI mientras trabajan — igual patrón que
el puente de memoria (`nucleo/mem_cli`). Lo invoca el CLI `nucleo/agent_report.py` (`hbnote`). Loopback/local: mismo
modelo de confianza que el resto de la API local.
"""
from fastapi import APIRouter, Body

router = APIRouter()


class _NotMine(Exception):
    """El que reporta NO es el dueño actual de este `task_id` (V2-350)."""


def _is_orphan(tid: str, token: str) -> bool:
    """¿Es este reporte de un worker HUÉRFANO — vivo, pero cuyo registro ya es de otro?

    Medido el 2026-08-26 en `search-buy-used-car`. El token de una tarea vive en su SessionRecord, así que para
    que no case tiene que haber un registro NUEVO con el mismo `task_id`: un relevo. El worker viejo sigue
    corriendo, y hasta hoy las dos puertas del motor le contestaban cosas distintas —

      · `/api/worker/act` (publicar en el widget, hablar) → **403**, «task/token no válido»
      · `/api/agent/report` (fase, progreso, plan, amplitud) → **no miraba el token**, así que escribía

    — que es exactamente al revés de lo que conviene: no podía ENTREGAR y sí podía CONTAMINAR. En la ronda
    medida, el huérfano tenía «7 coches con año/km verificados» que nunca llegaron a pantalla, mientras sus
    notas se escribían en el registro de su relevo: el estado del turno decía «selección final lista» 15 s
    después de que el worker nuevo naciera, y «el motor devuelve 403 al widget» como si fuera de este encargo.
    El juez lo leyó como un hecho de la ronda. Un instrumento que se cree las notas de un fantasma no mide.

    **Un token AUSENTE no es un token equivocado.** Sin él se sigue como siempre (fail-open): un worker que
    arrancó antes de este cambio, o un puente de un despliegue viejo, no puede quedarse mudo por una cabecera
    que nadie le enseñó a mandar. Lo que se corta es el token que NO CASA, que es la única señal inequívoca de
    que quien escribe ya no es el dueño.
    """
    if not (token or "").strip():
        return False
    try:
        from nucleo import dispatch
        rec = dispatch.get_record(tid)
        if rec is None:
            return False        # sin registro no hay estado que corromper; `session_*` ya sale de vacío
        return dispatch.rec_token(rec) != token
    except Exception:  # noqa: BLE001
        return False


@router.post("/api/agent/report")
async def agent_report(tid: str = Body(..., embed=True), token: str = Body("", embed=True),
                       phase: str = Body("", embed=True),
                       note: str = Body("", embed=True), plan: str = Body("", embed=True),
                       progress: str | None = Body(None, embed=True),
                       done: int | None = Body(None, embed=True), pct: int | None = Body(None, embed=True),
                       considered: int | None = Body(None, embed=True), kept: int | None = Body(None, embed=True)):
    """Un worker reporta su estado: `phase` = fase legible; `plan` = lista de tareas (pasos separados por |, V2-059);
    `progress`+`done`/`pct` = avance estructurado (→ ESTADO/prompt del FlashBrain + /api/tasks + UI); `note` = traza
    de observabilidad; `considered`/`kept` = AMPLITUD de una investigación (cuántos candidatos ha evaluado de verdad
    antes de quedarse con los finalistas). Best-effort; nunca rompe al agente."""
    orphan = _is_orphan(tid, token)
    if orphan:
        # NO SE TIRA NADA, se cuenta y se dice: lo del huérfano no toca el estado de su relevo, pero se ve. Si
        # desapareciera del todo, la próxima vez que pase nos quedaríamos sin la traza que lo delató esta.
        try:
            from voice.observer import emit
            _q = "; ".join(x for x in (phase.strip(), (progress or "").strip(), plan.strip()) if x)
            emit("task", "🚫 reporte de worker HUÉRFANO (no toca el estado)", text=_q[:200],
                 extra={"id": str(tid), "orphan": True})
        except Exception:  # noqa: BLE001
            pass
    try:
        from nucleo import dispatch
        if orphan:
            raise _NotMine      # a un huérfano no se le deja escribir en el ESTADO de su relevo (V2-350)
        if phase.strip():
            dispatch.session_phase(tid, phase.strip())
        if plan.strip():
            dispatch.session_plan(tid, plan.strip())
        if progress is not None or done is not None or pct is not None:
            dispatch.session_progress(tid, (progress or "").strip(), done=done, pct=pct)
        if considered is not None or kept is not None:
            dispatch.session_considered(tid, considered=considered, kept=kept)
    except Exception:
        pass
    if note.strip():
        try:
            from voice.observer import emit
            extra = {"id": str(tid)}
            # V2-044: este handler HTTP no tiene contexto de trace → sellar el de la sesión del worker.
            try:
                from nucleo import dispatch as _d
                _r = _d.get_record(tid)
                if _r is not None and _r.trace_id:
                    extra["trace"] = _r.trace_id
                    extra["span"] = f"worker:{tid}"
            except Exception:
                pass
            if orphan:
                extra["orphan"] = True
            emit("task", "note" if not orphan else "note (huérfano)", text=note.strip()[:200], extra=extra)
        except Exception:
            pass
    # Y SE LE DICE, que es la otra mitad. El 403 de `/api/worker/act` decía «task/token no válido» a secas y el
    # worker medido se pasó 45 s reintentando publicar, convencido de que el motor fallaba de forma intermitente
    # («403 intermitente», «403 persistente»): un error que no nombra la causa manda a reintentar lo mismo. Con
    # esto sabe que el encargo ya no es suyo y que lo que tenga hay que entregarlo por voz, no por la hoja.
    if orphan:
        return {"ok": False, "orphan": True,
                "error": "este encargo ya lo lleva otro worker (te han relevado): tus reportes no cuentan. NO "
                         "reintentes publicar — di por voz lo que tengas y termina."}
    return {"ok": True}
