"""The bridge's door: `POST /api/navegador/act` runs one action in a task's tab and returns the resulting state;
also the Process-tab phase of each action and the `extract` action. Names are read through the package
(`_f.<name>`), so a patch on `act_api` governs every call.
"""

import asyncio

from fastapi import Body
from fastapi.responses import JSONResponse
from nucleo.errors import brief as _brief
from nucleo.workers import progress as _progress
from widgets.navegador import lazy as _lazy
from widgets.results import door_verdict as _door

from widgets.navegador import act_api as _f


def _say_phase(nav_tid: str, phrase: str) -> None:
    """Set the OWNING session's phase from the browser side (V2-227 B1): «tengo resultados» is a milestone only the
    browser knows. Goes through `dispatch.session_phase`, the door `hbnote` uses — never a parallel rail."""
    try:
        from nucleo import dispatch as _d
        rec = _d.record_by_nav_task(str(nav_tid))
        if rec is not None and phrase:
            _d.session_phase(rec.task_id, phrase)
    except Exception:  # noqa: BLE001
        pass


def _phase_for_action(action: str, args: dict) -> str:
    """The PROCESS phrase for ONE browser action; empty means say nothing (V2-343). It reuses the existing
    vocabulary (`nucleo/workers/progress.phrase`, host included on navigate) — no new phrases here. The dedup in
    `sheets.record_phase` stays untouched: it is the counterweight that lets information through and not noise.
    """
    act = (action or "").strip().lower()
    if not act:
        return ""
    tgt = ""
    key = _f._PHASE_TARGET.get(act)
    if key:
        tgt = str((args or {}).get(key) or "")
    try:
        return _progress.phrase({"where": "navegador", "action": act, "target": tgt}) or ""
    except Exception:  # noqa: BLE001
        return ""


async def _act_extract(tb, task_id: str, args: dict) -> dict:
    """`extract{limit}`: the listings of the page, looked at again when it was half-hydrated or had not painted its
    cards yet, counted by the ones with a name, and handed over to the sheet and the conversation."""
    _limit = int(args.get("limit", 14))
    items = await tb.extract_listings(_limit)
    # V2-294 — rows with no identity are a half-hydrated listing (skeleton cards), not «no results»: look ONCE more.
    # Zero rows is not retried: that may be a truly empty search, and waiting on every empty one costs them all.
    if items and not _f.by_identity(items)[0]:
        await asyncio.sleep(_f._HYDRATE_WAIT_S)
        _retry = await tb.extract_listings(_limit)
        if _f.by_identity(_retry)[0]:
            _f._emit_nav(task_id, "🧭 resultados", "la página estaba a medio cargar; mirada otra vez")
            items = _retry
    # V2-323 — still nothing named: a VIRTUALISED listing may not have painted its cards yet. It only scrolls when
    # the page is taller than the screen (a truly empty search is not), and the view returns to its place.
    if not _f.by_identity(items)[0] and await _lazy.materialise_below_the_fold(tb.page):
        _tarde = await tb.extract_listings(_limit)
        if _f.by_identity(_tarde)[0]:
            _f._emit_nav(task_id, "🧭 resultados",
                      "la página pintaba sus fichas al acercarse; recorrida y mirada otra vez")
            items = _tarde
    # Count only the NAMED ones: «12 results» when nine are category links is a number the operator believes, and
    # `found(0)` says «no results here», which is what moves the worker to another site.
    _named, _unnamed = _f.by_identity(items)
    _extra = f" (+{len(_unnamed)} enlaces sin nombre)" if _unnamed else ""
    _f._emit_nav(task_id, "🧭 resultados", f"{len(_named)} anuncios/resultados en la página{_extra}")
    _f._say_phase(task_id, _progress.found(len(_named)))   # V2-227 B1: «12 results», the milestone he asked for
    _f._hand_over(task_id, items)      # V2-223: to the sheet and the conversation, not only to the worker
    return {"ok": True, "listings": items, "n": len(items), **_door.take(_f._sheet_of(task_id)), "url": str(getattr(tb.page, "url", "") or "")}  # V2-798: the SOURCE


@_f.router.post("/api/navegador/act")
async def navegador_act(task_id: str = Body(..., embed=True), action: str = Body(..., embed=True),
                        args: dict = Body(default_factory=dict, embed=True)):
    """Execute one browser action in the `task_id` tab and return resulting state so the agent can reason about the
    next step. Actions: snapshot | navigate{url} | click{ref} | type{ref,text,submit} | scroll{dy} | press{key} |
    extract{limit}. `click`/`type` use refs from the latest snapshot, so request snapshot before acting. The owner's
    confirmation gate for irreversible actions still applies. Best-effort: never raises."""
    action = (action or "").strip()
    args = args or {}
    # V2-343: the phase is said BEFORE executing — the operator needs «entrando en coches.net» while it happens; a
    # failed action already has its own row.
    _f._say_phase(task_id, _f._phase_for_action(action, args))
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
            return {"ok": True, "shot": _f._shot_path(task_id), **_f._with_stall(task_id, _f._with_wall(snap, task_id))}
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
            _f._emit_nav(task_id, "🧭 vista", f"captura {snap.get('title') or snap.get('url') or ''}"[:200])
            return {"ok": True, "shot": _f._shot_path(task_id), "viewport": {"width": 1280, "height": 800},
                    **_f._with_stall(task_id, _f._with_wall(snap, task_id))}
        if action == "visit":
            # READ ONE LISTING WITHOUT LOSING THE LIST. It comes before `extract` because they share the idea of
            # «what is on this page», but not the tab: `visit` opens its own and closes it.
            got = await tb.visit(str(args.get("url", "")), int(args.get("chars", 2500)))
            if got.get("ok"):
                _f._emit_nav(task_id, "🧭 ficha", f"{str(got.get('title') or got.get('url'))[:150]}")
            else:
                _f._emit_nav(task_id, "🧭 ficha ⚠️ error", str(got.get("error"))[:150])
            return got
        if action == "extract":
            return await _f._act_extract(tb, task_id, args)
        if action in ("navigate", "click", "type", "select_option", "scroll", "press", "click_at", "type_at"):
            # The address BEFORE, to tell what changed (V2-293). Read from the tab's record
            # because it is all that survives between bridge calls: `nav_cli` is one process per action.
            _before = ""
            try:
                from widgets.navegador import tasks as _t0
                _before = str((_t0.get(task_id) or {}).get("url") or "")
            except Exception:
                pass
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
                _f._emit_nav(task_id, "🧭 página", page)
            # Fresh PNG path; every action calls _capture, so the worker can Read the view after acting.
            return {"ok": bool(ok), "msg": msg, "shot": _f._shot_path(task_id),
                    **_f._with_stall(task_id, _f._with_wall(_f._with_url_change(_before, snap), task_id))}
        return JSONResponse({"ok": False, "error": f"acción desconocida: {action}"}, status_code=400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {_brief(e, 160)}"},
                            status_code=500)
