"""nucleo/agent_api.py — CANAL DE REPORTE de los agentes Claude Code hacia el proceso vivo (V2-036).

Los workers Claude Code son SUBPROCESOS: no comparten el bus/estado in-process del server. Este endpoint es el
puente por HTTP para que reporten su PROGRESO (fase) y datos al FlashBrain/UI mientras trabajan — igual patrón que
el puente de memoria (`nucleo/mem_cli`). Lo invoca el CLI `nucleo/agent_report.py` (`hbnote`). Loopback/local: mismo
modelo de confianza que el resto de la API local.
"""
from fastapi import APIRouter, Body

router = APIRouter()


@router.post("/api/agent/report")
async def agent_report(tid: str = Body(..., embed=True), phase: str = Body("", embed=True),
                       note: str = Body("", embed=True), plan: str = Body("", embed=True),
                       progress: str | None = Body(None, embed=True),
                       done: int | None = Body(None, embed=True), pct: int | None = Body(None, embed=True),
                       considered: int | None = Body(None, embed=True), kept: int | None = Body(None, embed=True)):
    """Un worker reporta su estado: `phase` = fase legible; `plan` = lista de tareas (pasos separados por |, V2-059);
    `progress`+`done`/`pct` = avance estructurado (→ ESTADO/prompt del FlashBrain + /api/tasks + UI); `note` = traza
    de observabilidad; `considered`/`kept` = AMPLITUD de una investigación (cuántos candidatos ha evaluado de verdad
    antes de quedarse con los finalistas). Best-effort; nunca rompe al agente."""
    try:
        from nucleo import dispatch
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
            emit("task", "note", text=note.strip()[:200], extra=extra)
        except Exception:
            pass
    return {"ok": True}
