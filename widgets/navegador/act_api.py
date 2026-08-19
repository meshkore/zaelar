"""widgets/navegador/act_api.py: BROWSER BRIDGE for Claude Code agents (V2-036 F3).

Exposes the owner's `TaskBrowser` primitives as a synchronous request/response API so a headless Claude Code agent
can drive zaelar's Chromium step by step (navigate/click/type/scroll/snapshot/extract) with its own intelligence.
This replaces the cheap DOM->vision loop (Haiku). It runs in the uvicorn loop, the same loop as the backed browser
owner, so it can call `TaskBrowser` methods directly rather than through the fire-and-forget mailbox. Invoked by
the `nucleo/nav_cli.py` CLI (`hbweb`). Local/loopback: same trust model as the rest of the API.
"""
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

router = APIRouter()


def _shot_path(task_id: str) -> str:
    """Absolute PNG path for this tab's viewport, written by TaskBrowser._capture after each action, so the worker
    can read it with Read. Best-effort: if anything fails, return '' and the worker continues with text snapshot."""
    try:
        import os
        from widgets import store
        from widgets.navegador import owner
        return os.path.abspath(f"{store.data_dir(owner.WID)}/shot-{task_id}.png")
    except Exception:
        return ""


def _emit_nav(nav_tid: str, label: str, text: str) -> None:
    """V2-048: observability row for a browser action result: which page it reached / what it found. This is what
    the command itself does NOT say and only the browser knows. Label differs from the intent `step`, avoiding
    collisions with `navegador` flood-dedup. Stamps trace/span for the worker owning the tab. Best-effort, never
    raises."""
    try:
        from voice.observer import emit
        from nucleo import dispatch
        extra = {"id": nav_tid}
        r = dispatch.record_by_nav_task(nav_tid)
        if r is not None and getattr(r, "trace_id", ""):
            extra["trace"] = r.trace_id
            extra["span"] = f"worker:{r.task_id}"
        emit("navegador", label, text=text[:200], extra=extra)
    except Exception:
        pass


@router.post("/api/navegador/act")
def _with_wall(snap: dict) -> dict:
    """Annotate a snapshot with `wall` when the page it landed on STOPPED us (anti-bot challenge, CAPTCHA, load
    error) — V2-167.

    The worker drives through this endpoint and its only view of the page is what comes back here, so a wall it
    cannot see is a wall it grinds against. Measured: a run spent three minutes re-photographing Booking's
    `chal_t=` challenge and another walked through Google's `/sorry/index`, and both reported no obstacle at all.
    The rule telling the worker what to do about a captcha already existed (`nucleo/dispatch_prompts.py`); what
    was missing was any way for it to know it was looking at one.
    """
    try:
        from widgets.navegador import tasks as _t
        reason = _t.wall_reason(str((snap or {}).get("url") or ""))
    except Exception:
        return snap
    if reason:
        snap = dict(snap or {})
        snap["wall"] = reason
    return snap

async def navegador_act(task_id: str = Body(..., embed=True), action: str = Body(..., embed=True),
                        args: dict = Body(default_factory=dict, embed=True)):
    """Execute one browser action in the `task_id` tab and return resulting state so the agent can reason about the
    next step. Actions: snapshot | navigate{url} | click{ref} | type{ref,text,submit} | scroll{dy} | press{key} |
    extract{limit}. `click`/`type` use refs from the latest snapshot, so request snapshot before acting. The owner's
    confirmation gate for irreversible actions still applies. Best-effort: never raises."""
    action = (action or "").strip()
    args = args or {}
    try:
        from widgets.navegador import owner
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"navegador no disponible: {e}"}, status_code=503)
    try:
        tb = owner._task_browsers.get(task_id)
        if tb is None:
            tb = owner.TaskBrowser(task_id)
            owner._task_browsers[task_id] = tb
        await tb.ensure()

        if action == "snapshot":
            snap = await tb.snapshot_for_agent()
            return {"ok": True, "shot": _shot_path(task_id), **_with_wall(snap)}
        if action == "look":
            # V2-049 VISION: fresh viewport capture to disk. The worker reads it with its Read tool, sees the page
            # like a human, and acts by coordinates (click_at/type_at). This is the robust path for forms,
            # date-pickers, and selects that the text snapshot cannot describe well enough.
            await tb._capture()
            snap = {}
            try:
                snap = await tb.snapshot_for_agent()
            except Exception:
                pass
            _emit_nav(task_id, "🧭 vista", f"captura {snap.get('title') or snap.get('url') or ''}"[:200])
            return {"ok": True, "shot": _shot_path(task_id), "viewport": {"width": 1280, "height": 800},
                    **_with_wall(snap)}
        if action == "extract":
            items = await tb.extract_listings(int(args.get("limit", 14)))
            _emit_nav(task_id, "🧭 resultados", f"{len(items)} anuncios/resultados en la página")
            return {"ok": True, "listings": items, "n": len(items)}
        if action in ("navigate", "click", "type", "select_option", "scroll", "press", "click_at", "type_at"):
            ok, msg = await tb.agent_act(action, args)
            # Return fresh state after the action so the agent sees the result and decides the next step.
            snap = {}
            try:
                snap = await tb.snapshot_for_agent()
            except Exception:
                pass
            # Observability: which page the action reached (title + url); only the browser knows this (V2-048).
            page = " · ".join(x for x in (str(snap.get("title") or "").strip(),
                                          str(snap.get("url") or "").strip()) if x)
            if page:
                _emit_nav(task_id, "🧭 página", page)
            # Fresh PNG path; every action calls _capture, so the worker can Read the view after acting.
            return {"ok": bool(ok), "msg": msg, "shot": _shot_path(task_id), **_with_wall(snap)}
        return JSONResponse({"ok": False, "error": f"acción desconocida: {action}"}, status_code=400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"},
                            status_code=500)
