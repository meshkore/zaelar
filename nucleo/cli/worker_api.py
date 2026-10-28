"""nucleo/cli/worker_api.py — REQUEST/RESPONSE blueprint for Brain Workers (V2-038, §v2·B + §v3·I/J/K).

A worker subprocess talks to the live server over HTTP to request what only the host can do: `ask_user` (ask the
operator and WAIT), `use_tool` (a FILTERED FlashBrain tool, §v3·J — web_search today), `read_widget`/`show_widget`/
`close_widget`, `push_channel` (CONFIRM + scan_outbound) and `spawn` (within quota/depth).

ONE endpoint, ALLOW/CONFIRM/DENY policy evaluated HERE (not in the worker prompt), CONFIRM = an auto-generated
`ask_user` (§v3·K), idempotent re-poll (§v3·I), per-task token auth (§v2·D), and every response carries the pending
FlashBrain injections (piggyback, §v3·H). Execution lives in `worker_api_exec`, the ask registry's logic in
`worker_api_asks`; both are re-exported here.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from nucleo.runtime_ids import next_seq as _next_seq

router = APIRouter()


# ── per-action policy (§v3·J): pure logic in worker_policy.py, re-exported (`worker_api.classify_act(...)`) ─────
from nucleo.cli.worker_policy import (  # noqa: F401,E402 — re-export
    ALLOW, CONFIRM, DENY, _PRESTABLE_TOOLS, _DENY_TOOLS, _KNOWN_ACTS, deny_reason, classify_act,
    _confirm_question,
)
_MAX_DEPTH = 2


# ── in-flight request registry (corr_id → state) ────────────────────────────────────────────────────────────
_ACTS: dict[str, dict] = {}
_ANSWERED_TTL_S = 600.0

#: How many reminders ONE task may schedule — the capability's filter: a looping worker cannot fill the agenda.
_SCHEDULE_CAP = 3

#: The forms the parser REALLY accepts, said once for all three errors (examples that don't parse send it to retry).
_CUANDO_VALE = ('Vale «mañana a las 9», «el miércoles a las 18:00», un día del mes («el 3 a las 10»), '
                '«every 30m» para algo que se repite, o un cron de 5 campos «0 9 * * 3».')


def _new_corr(task_id: str, action: str) -> str:
    """UNPREDICTABLE corr_id: the re-poll carries no token, so the corr IS the capability (§v2·D)."""
    return f"{task_id}:{action}:{_next_seq('worker_api.corr')}:{secrets.token_urlsafe(8)}"


def _piggyback(task_id: str) -> list[str]:
    """Pending FlashBrain injections for this worker (§v3·H) — served in ANY bridge response."""
    try:
        from nucleo import dispatch
        return dispatch.take_pending_injects(task_id)
    except Exception:
        return []


def _verify(task_id: str, token: str):
    """Return the SessionRecord if the token matches; None otherwise (per-task auth, §v2·D)."""
    try:
        from nucleo import dispatch
        rec = dispatch.get_record(task_id)
        if rec is None:
            return None
        # constant-time: the per-task token is the bridge's only credential, and `!=` leaks its prefix by timing
        if not secrets.compare_digest(dispatch.rec_token(rec).encode(), str(token or "").encode()):
            return None
        return rec
    except Exception:
        return None


# ── endpoints ────────────────────────────────────────────────────────────────────────────────────────────
@router.post("/api/worker/act")
async def worker_act(task_id: str = Body(..., embed=True), token: str = Body("", embed=True),
                     action: str = Body(..., embed=True), payload: dict = Body(default={}, embed=True)):
    """The worker requests an action. Verify token → policy → execute (immediate ALLOW), park (ask/CONFIRM), or
    deny. Always carries the injection piggyback."""
    rec = _verify(task_id, token)
    inj = _piggyback(task_id)
    if rec is None:
        return JSONResponse({"ok": False, "error": "task/token no válido", "injections": inj}, status_code=403)

    pol = classify_act(action, payload)
    if pol == DENY:
        return JSONResponse({"ok": False, "denied": True,
                             "error": deny_reason(action, payload), "injections": inj})

    if action == "ask_user":
        q = (payload or {}).get("question") or (payload or {}).get("text") or ""
        corr = _register_ask(rec, str(q))
        return JSONResponse({"ok": True, "status": "pending", "corr_id": corr, "injections": inj})

    from nucleo import on_his_behalf as _behalf      # an act in his name he never asked for is a question
    _q_behalf = _behalf.worker_question(rec, action, payload) if pol == ALLOW else ""
    if pol == CONFIRM or _q_behalf:
        # §v3·K: an irreversible act becomes an auto-generated ask_user with the RETAINED action.
        q = _q_behalf or _confirm_question(action, payload)
        corr = _register_ask(rec, q, action=action, retained={"action": action, "payload": payload})
        return JSONResponse({"ok": True, "status": "pending", "corr_id": corr, "injections": inj})

    from nucleo import network_rows_gate as _net     # a network agent's rows never open a sheet for a report
    if (_skip := _net.refused(rec, action, payload)):
        return JSONResponse({"ok": True, "skipped": _skip, "injections": inj})
    from nucleo import circuit as _deliv    # an errand opens only its deliverable (V2-822)
    if (_why := _deliv.refused(rec, action, payload)):
        return JSONResponse({"ok": False, "error": _why, "injections": inj})
    res = await _exec_allow(action, payload or {}, rec)
    res["injections"] = inj
    return JSONResponse(res)


@router.post("/api/worker/say")
async def worker_say(task_id: str = Body(..., embed=True), token: str = Body("", embed=True),
                     text: str = Body("", embed=True)):
    """The worker SAYS something to the user (EXPLICIT say, §v2·E·Q3) — recounted by voice+UI with attribution. Piggyback."""
    rec = _verify(task_id, token)
    inj = _piggyback(task_id)
    if rec is None:
        return JSONResponse({"ok": False, "error": "task/token no válido", "injections": inj}, status_code=403)
    msg = (text or "").strip()
    if msg:
        try:
            import bus
            bus.emit_sync("worker.say", {"id": task_id, "text": msg[:400]})
        except Exception:
            pass
        try:
            from voice import proactive
            # an INTERIM word: said if there is a quiet moment, otherwise it stays on screen and never rides his
            # next answer (questions go through `ask`, the result through the delivery — both unaffected)
            await proactive.notify("zaelar", msg, speak=True, carry=False)
        except Exception:
            pass
    return JSONResponse({"ok": True, "injections": inj})


@router.get("/api/worker/act/{corr_id}")
async def worker_act_poll(corr_id: str):
    """Idempotent re-poll (§v3·I): state of a parked request. The response is stored until claimed."""
    e = _ACTS.get(corr_id)
    tid = (e or {}).get("task_id", "")
    inj = _piggyback(tid) if tid else []
    if not e:
        return JSONResponse({"ok": False, "error": "corr_id desconocido", "injections": inj}, status_code=404)
    if e["state"] == "answered":
        return JSONResponse({"ok": True, "status": "answered", "answer": e.get("answer", ""),
                             "result": e.get("result"), "injections": inj})
    return JSONResponse({"ok": True, "status": "pending", "injections": inj})


from nucleo.cli.worker_api_exec import (  # noqa: E402,F401 — moved by concern (refactor2710-10b)
    _own_sheet, _decide_deadline, _exec_allow, _spawn_child,
)
from nucleo.cli.worker_api_asks import (  # noqa: E402,F401 — moved by concern (refactor2710-10b)
    purge_task, _prune, _register_ask, has_pending_ask, pending_asks, active_ask, answer, answer_active,
    answer_active_soon, _clear_waiting, _is_yes,
)
