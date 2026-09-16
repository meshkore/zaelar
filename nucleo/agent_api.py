"""nucleo/agent_api.py — the REPORTING CHANNEL from Claude Code workers back into the live process (V2-036).

Claude Code workers are SUBPROCESSES: they do not share the server's in-process bus or state. This endpoint is
the HTTP bridge they report their PROGRESS (phase, plan, advance) and data through to the FlashBrain and the
UI while they work — the same pattern as the memory bridge (`nucleo/mem_cli`). It is called by the
`nucleo/agent_report.py` CLI (`hbnote`). Loopback/local: the same trust model as the rest of the local API.

⚠️ Its comments and every docstring were lost on 2026-08-31 (`87874bd7`, the comment-translation batch) and
re-grafted by hand in V2-711 T0.7. The one that matters most is `_is_orphan`'s, below: it records why THIS
door checks the token at all.
"""
from fastapi import APIRouter, Body

router = APIRouter()


class _NotMine(Exception):
    """Whoever is reporting is NOT the current owner of this `task_id` (V2-350)."""


def _is_orphan(tid: str, token: str) -> bool:
    """Is this report from an ORPHAN worker — alive, but whose record already belongs to somebody else?

    Measured 2026-08-26 in `search-buy-used-car`. A task's token lives in its SessionRecord, so for it not to
    match there has to be a NEW record under the same `task_id`: a relief. The old worker keeps running, and
    until then the engine's two doors answered it differently —

      · `/api/worker/act` (publish to the widget, speak) → **403**, «task/token not valid»
      · `/api/agent/report` (phase, progress, plan, breadth) → **did not look at the token**, so it wrote

    — which is exactly backwards: it could not DELIVER and it could CONTAMINATE. In the round that was
    measured, the orphan had «7 cars with verified year/mileage» that never reached the screen, while its
    notes were written into its RELIEF's record: the turn's state said «final selection ready» 15 s after the
    new worker was born, and «the engine returns 403 to the widget» as though it belonged to this errand. The
    judge read it as a fact of the round. An instrument that believes a ghost's notes does not measure.

    **An ABSENT token is not a WRONG token.** Without one everything proceeds as before (fail-open): a worker
    that started before this change, or a bridge from an older deployment, must not be struck dumb by a header
    nobody taught it to send. What is cut off is the token that does NOT MATCH, which is the only unambiguous
    signal that the writer is no longer the owner."""
    if not (token or "").strip():
        return False
    try:
        from nucleo import dispatch
        rec = dispatch.get_record(tid)
        if rec is None:
            return False        # with no record there is no state to corrupt; `session_*` already
                                # answers from empty
        return dispatch.rec_token(rec) != token
    except Exception:  # noqa: BLE001
        return False


@router.post("/api/agent/report")
async def agent_report(tid: str = Body(..., embed=True), token: str = Body("", embed=True),
                       phase: str = Body("", embed=True),
                       note: str = Body("", embed=True), plan: str = Body("", embed=True),
                       progress: str | None = Body(None, embed=True),
                       done: int | None = Body(None, embed=True), pct: int | None = Body(None, embed=True),
                       considered: int | None = Body(None, embed=True), kept: int | None = Body(None, embed=True),
                       done_when: dict | None = Body(None, embed=True)):
    """A worker reports its state: `phase` = a readable phase; `plan` = its task list (steps separated by |,
    V2-059); `progress` + `done`/`pct` = structured advance (→ the FlashBrain's STATE/prompt + /api/tasks +
    the UI); `note` = an observability trace; `considered`/`kept` = the BREADTH of an investigation (how many
    candidates it really evaluated before keeping the finalists). Best-effort; it never breaks the agent."""
    orphan = _is_orphan(tid, token)
    if orphan:
        # NOTHING IS THROWN AWAY, it is counted and SAID: an orphan's report does not touch the state of
        # the worker that relieved it, but it stays visible. If it disappeared entirely, the next time
        # this happened we would be without the trace that gave it away this time.
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
            raise _NotMine      # an orphan does not get to write in the STATE of its relief (V2-350)
        if phase.strip():
            dispatch.session_phase(tid, phase.strip())
        if plan.strip():
            dispatch.session_plan(tid, plan.strip())
        if progress is not None or done is not None or pct is not None:
            dispatch.session_progress(tid, (progress or "").strip(), done=done, pct=pct)
        if considered is not None or kept is not None:
            dispatch.session_considered(tid, considered=considered, kept=kept)
        # V2-707 F2 — HOW SUCCESS IS MEASURED, declared by the worker itself at the start. `_finish` reads
        # it against the product's own truth before delivering, so a task cannot end by SAYING it is done.
        if isinstance(done_when, dict) and done_when:
            from nucleo.workers.goal import session_goal
            session_goal(tid, done_when)
    except Exception:
        pass
    if note.strip():
        try:
            from voice.observer import emit
            extra = {"id": str(tid)}
            # V2-044: this HTTP handler has no trace context → stamp the worker session's own.
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
    # AND IT IS SAID TO IT, which is the other half. `/api/worker/act`'s 403 said «task/token not valid»
    # and nothing else, and the worker that was measured spent 45 s retrying the publish, convinced the
    # engine was failing intermittently («intermittent 403», «persistent 403»): an error that does not
    # name its cause sends you back to retry the same thing. With this it knows the errand is no longer
    # its own, and that whatever it has must be delivered by voice, not through the sheet.
    if orphan:
        return {"ok": False, "orphan": True,
                "error": "este encargo ya lo lleva otro worker (te han relevado): tus reportes no cuentan. NO "
                         "reintentes publicar — di por voz lo que tengas y termina."}
    return {"ok": True}
