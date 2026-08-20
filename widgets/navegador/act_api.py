"""widgets/navegador/act_api.py: BROWSER BRIDGE for Claude Code agents (V2-036 F3).

Exposes the owner's `TaskBrowser` primitives as a synchronous request/response API so a headless Claude Code agent
can drive zaelar's Chromium step by step (navigate/click/type/scroll/snapshot/extract) with its own intelligence.
This replaces the cheap DOM->vision loop. It runs in the uvicorn loop, the same loop as the backed browser
owner, so it can call `TaskBrowser` methods directly rather than through the fire-and-forget mailbox. Invoked by
the `nucleo/nav_cli.py` CLI (`hbweb`). Local/loopback: same trust model as the rest of the API.
"""
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

router = APIRouter()


def _shot_path(task_id: str) -> str:
    """Absolute PNG path for this tab's viewport, written by TaskBrowser._capture after each action, so the worker
    can read it with Read. Best-effort: if anything fails, return '' and the worker continues with text snapshot.

    V2-205 — it used to return the path whether or not the PNG was THERE, and `nav_cli` turns a non-empty value
    into an instruction: «MÍRALA con Read "<path>"». So every action taken before the first successful capture
    —or after one that failed— sent the worker to read a file that does not exist. Measured in two independent
    runs (`find-theatre-tickets__es` 15:06, and the same family reported on `cheapest-monitor`):

        worker/task «📄 archivo ⚠️ error»: File does not exist.
        Note: your current working directory is /private/var/.../T/zaelar-workers/2

    The path was never the problem — it is absolute, and V2-117 confirmed the CLI already allows reading outside
    the working directory. What was wrong is ADVERTISING it. The text snapshot is the documented fallback right
    here in this docstring; an empty return takes it, and `nav_cli` simply prints no VISTA line.
    """
    try:
        import os
        from widgets import store
        from widgets.navegador import owner
        p = os.path.abspath(f"{store.data_dir(owner.WID)}/shot-{task_id}.png")
        return p if os.path.isfile(p) else ""
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


# Same threshold the FlashBrain turn uses for «sin moverse» (`nucleo/flash/prompt.py`), read from the same env
# var so the two halves of one fact can never drift apart.
_STALL_HINT_S = int(__import__("os").environ.get("ZAELAR_NAV_STALLED_S", "120") or 120)


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


def _with_stall(task_id: str, snap: dict) -> dict:
    """Tell the worker how long its own task has gone WITHOUT MOVING — the half of V2-167 that never reached it.

    The wall travels to the worker (above) and the stall did not, which left the two halves of the same fact in
    different places: the FlashBrain turn learned that a task had stopped moving, and the only party that could
    do anything about it did not.

    Measured on `find-theatre-tickets__es` (2026-08-20 01:01): the worker navigated seven times, landed on the
    right event page at 00:40:32, and then took FOURTEEN screenshot revisions of it without a single further
    navigation for roughly twenty minutes. It was not blocked and it was not idle — it was looking at the page
    over and over. Nothing in what came back from here said «you have been here a while», so from inside the
    loop every `look` was as good as the first. Same shape on `restaurant-tonight-madrid`: eleven minutes and
    ten captures of one page.

    Only reported past the same threshold the turn uses, so an ordinary page-by-page pass says nothing.
    """
    try:
        from widgets.navegador import tasks as _t
        stalled = int((_t.get(task_id) or {}).get("stalled_s") or 0) if hasattr(_t, "get") else 0
        if not stalled:
            for _p in _t.active_progress():
                if str(_p.get("id") or "") == str(task_id):
                    stalled = int(_p.get("stalled_s") or 0)
                    break
    except Exception:
        return snap
    if stalled >= _STALL_HINT_S and not (snap or {}).get("wall"):
        snap = dict(snap or {})
        snap["stalled_s"] = stalled
        snap["hint"] = (f"llevas {stalled // 60} min en esta página sin avanzar: o extraes ya lo que necesitas "
                        f"de lo que tienes delante, o pruebas otro sitio. Repetir `look` no la cambia.")
    return snap


@router.post("/api/navegador/act")
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
            return {"ok": True, "shot": _shot_path(task_id), **_with_stall(task_id, _with_wall(snap))}
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
                    **_with_stall(task_id, _with_wall(snap))}
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
            return {"ok": bool(ok), "msg": msg, "shot": _shot_path(task_id), **_with_stall(task_id, _with_wall(snap))}
        return JSONResponse({"ok": False, "error": f"acción desconocida: {action}"}, status_code=400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"},
                            status_code=500)
