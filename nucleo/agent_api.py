"""Documentation translated to English."""
from fastapi import APIRouter, Body

router = APIRouter()


class _NotMine(Exception):
    """Documentation translated to English."""


def _is_orphan(tid: str, token: str) -> bool:
    """Documentation translated to English."""
    if not (token or "").strip():
        return False
    try:
        from nucleo import dispatch
        rec = dispatch.get_record(tid)
        if rec is None:
            return False        # translated implementation note
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
    """Documentation translated to English."""
    orphan = _is_orphan(tid, token)
    if orphan:
        # translated implementation note
        # translated implementation note
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
            raise _NotMine      # translated implementation note
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
            # translated implementation note
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
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    if orphan:
        return {"ok": False, "orphan": True,
                "error": "este encargo ya lo lleva otro worker (te han relevado): tus reportes no cuentan. NO "
                         "reintentes publicar — di por voz lo que tengas y termina."}
    return {"ok": True}
