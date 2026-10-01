"""The canvas routes: what is on screen, the layout and the arrange order (V2-778 F1, 2026-10-01).

Moved out of `server/voice_api.py` (994 lines, over the 900 a new file may reach): `/api/canvas/state`,
`/api/canvas/arrange`, `/api/canvas/layout` and their helpers, unchanged, on their own router (mounted next to
voice_api's in `server/__init__.py`). `voice_api` imports every name back, so `voice_api.open_instances()` and
every `from server.voice_api import …` keep working.
"""
from __future__ import annotations

import os
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from voice.observer import emit

router = APIRouter()


@router.post("/api/canvas/state")
async def canvas_state(payload: dict):
    """The frontend (authoritative for the canvas) reports which widgets the operator has OPEN → stored in memory
    STATE (`open_widgets`), which ALWAYS travels in the prompt (memory_cache) and appears in the map. This lets the
    brain know "what the operator has in front of them" and resolve "modify the X widget" without asking.
    Best-effort, fire-and-forget from `desktop._persist()`. Normalizes instance ids (navegador::t3 → navegador)
    and dedupes."""
    # THE SCREEN THE CONVERSATION IS ABOUT is the one holding the voice session. Two tabs (or a phone and a
    # desktop) report different canvases, and the server used to take the last word: in the demo pass of
    # 2026-09-28 the operator's watching tab, which had no chart, «closed» Markets 268 ms into «ok close that»,
    # the verdict no longer saw the chart and the agenda was closed instead. While a live session holds the
    # lock, another tab's report is not the operator's screen. No live session → every report counts, as before.
    try:
        from server import livekit_api as _lk
        _sid = str((payload or {}).get("sid") or "")
        # (a report with NO sid is a tab older than this rule — the voice tab always carries one)
        if _lk._active.get("sid") and not _lk._free(time.time()) and _lk._active["sid"] != _sid:
            return JSONResponse({"ok": True, "ignored": "not the screen of the voice session"})
    except Exception:  # noqa: BLE001
        pass
    raw = payload.get("open") or []
    seen: list[str] = []
    inst: list[str] = []                        # V2-047 F9: full INSTANCE ids, as-is (navegador::t1)
    for wid in raw:
        w = str(wid or "").strip()
        if w and w not in inst:
            inst.append(w)
        base = w.split("::", 1)[0].strip().lower()
        if base and base not in seen:
            seen.append(base)
    # V2-047 F9 (23:15 session, "two browsers, one blank"): the NORMALIZED set collapses navegador::t1 and
    # navegador::t2 into one "navegador" → it was impossible afterwards to know whether there were really TWO
    # cards. Record raw instances in a `ui` event (cheap, only when the canvas changes) for diagnostics.
    try:
        from voice.observer import emit as _emit_inst
        _prev_inst = getattr(canvas_state, "_last_inst", None)
        canvas_state._last_inst = inst          # V2-259 F3: ALWAYS, not only when it changes — see open_instances()
        if inst != _prev_inst:
            _emit_inst("ui", "canvas (instancias)", role="user",
                       extra={"instances": inst, "n": len(inst), "cat": "main"})
    except Exception:
        pass
    # V2-039 — AUDIT of the OPERATOR's canvas orders: the frontend is authoritative and reports the OPEN set on each
    # change; comparing it with the previous set tells us what the user opened/closed (manually, by dragging, or via
    # the close button), and we record it on the timeline with "user" provenance — these used to be SILENT actions.
    try:
        from memory import api as memory
        prev = set((memory.state() or {}).get("open_widgets") or [])
        now = set(seen)
        from voice.observer import emit
        # V2-044: a MANUAL operator action on the canvas is also a stimulus → it gets its trace (origin="ui").
        # Fresh HTTP context per request — the ctxvar remains scoped by itself. Only when there is a real diff.
        if (now - prev) or (prev - now):
            try:
                from voice import trace as _trace
                _delta = [f"+{w}" for w in sorted(now - prev)] + [f"−{w}" for w in sorted(prev - now)]
                _trace.begin("canvas: " + " ".join(_delta), origin="ui")
            except Exception:
                pass
        for wid in (now - prev):
            emit("widget", "show", extra={"id": wid, "src": "user"})
        for wid in (prev - now):
            emit("widget", "close", extra={"id": wid, "src": "user"})
        # V2-609 — WHICH card is at full screen, if any. It is not geometry (the brain does not care about
        # coordinates, which is why `layout` goes to sys_kv): it is «what the operator has in front of them»,
        # the same class of fact `open_widgets` exists for. Without it «sal de pantalla completa» named no
        # target, `fullscreen_widget` required one, and the turn answered «Hecho.» having done nothing
        # (measured live 2026-09-07 18:54:27). Normalized like the rest, so an instance card answers too.
        _maxw = ""
        try:
            for it in ((payload or {}).get("layout") or [])[:40]:
                if isinstance(it, dict) and it.get("max"):
                    _maxw = str(it.get("id") or "").split("::", 1)[0].strip().lower()
                    break
        except Exception:  # noqa: BLE001
            _maxw = ""
        # …and which ones are MINIMIZED: open on the canvas, not on the screen (full27 S1: «show me» over the
        # minimized sheet was suppressed as «already open», and «here they are» spoke over nothing visible).
        _minw: list = []
        try:
            for it in ((payload or {}).get("layout") or [])[:40]:
                if isinstance(it, dict) and it.get("min"):
                    _m = str(it.get("id") or "").split("::", 1)[0].strip().lower()
                    if _m and _m not in _minw:
                        _minw.append(_m)
        except Exception:  # noqa: BLE001
            _minw = []
        memory.set_state({"open_widgets": seen, "maximized_widget": _maxw, "minimized_widgets": _minw})
        # V2-078: widgets that BECOME open enter the `recent_widgets` MRU (2nd scoping layer open>recent>catalog).
        # It persists after closing → "the one I used a moment ago" still has priority. Single hook: every show
        # (from the operator OR the brain via [[show]]) re-reports the canvas here.
        if (now - prev):
            try:
                memory.note_widgets_used(sorted(now - prev))
            except Exception:
                pass
    except Exception:  # noqa: BLE001
        pass
    # DESKTOP REHYDRATION (2026-08-12): the frontend also sends GEOMETRY (which card, where, with which query) and
    # it is saved as a SAFETY NET for `localStorage`, which is where restoration normally comes from. localStorage is
    # per-ORIGIN and per-browser: the same zaelar served at `https://local.zaelar.com:44317` and
    # `http://localhost:43917` are two different desktops, and another browser/profile has none. When the operator
    # thinks "the desktop was lost", they are almost always looking at an empty store that is not theirs. It goes to
    # `sys_kv` (UI state, NOT the root state that travels in every prompt: the brain does not care about a card's
    # coordinates). It is only WRITTEN here; `GET /api/canvas/layout` restores it.
    try:
        items = (payload or {}).get("layout")
        if isinstance(items, list):
            from memory import api as memory
            clean = []
            for it in items[:40]:
                if not isinstance(it, dict) or not str(it.get("id") or "").strip():
                    continue
                # w/h included since V2-630: a size the operator set is part of "where he left it" — dropping
                # them made a cross-browser restore fall back to auto-size, the exact dance the rule forbids.
                clean.append({k: str(it.get(k) or "")[:120] for k in ("id", "q", "left", "top", "z", "w", "h", "min", "t")})
            memory.kv_set("canvas_layout", {"at": time.time(), "items": _prune_ghost_sheets(clean)})
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse({"ok": True, "open_widgets": seen})


def _sheet_ids_on_disk() -> list:
    """The results sheets that HAVE data (a `state.json`), as canvas ids. A bare `results--x` directory is not
    one: `store.data_dir()` creates it on the first read, which is exactly what a ghost card's own fetch does."""
    out: list = []
    try:
        from widgets import store as _st
        for name in sorted(os.listdir(_st.DATA_DIR)):
            if name.startswith("results--") and os.path.exists(os.path.join(_st.DATA_DIR, name, "state.json")):
                out.append(_st.canvas_id(name))
    except Exception:  # noqa: BLE001
        pass
    return out


def _prune_ghost_sheets(items: list, live: list | None = None) -> list:
    """Drop the results sheets nothing stands behind (V2-773, 2026-09-27). After `make reset` the operator's
    tab, open across it, re-reported its old cards and the server saved them again; every tab with no desktop
    of its own then rehydrated four empty «Resultados» from here, and their own reads recreated their folders.
    A sheet is real when its data is on disk or its errand is live; anything else named `results::…` is a ghost."""
    live_set = set(str(x) for x in (live if live is not None else _live_canvas_instances()))
    on_disk = set(_sheet_ids_on_disk())
    out = []
    for it in items or []:
        cid = str((it.get("id") if isinstance(it, dict) else it) or "")
        if cid.startswith("results::") and cid not in on_disk and cid not in live_set:
            continue
        out.append(it)
    return out


def _live_canvas_instances() -> list:
    """The instance cards of work running RIGHT NOW (V2-351): the sheet of every live errand whose surface is
    the results sheet, plus every browser-tab card the server holds. This is what a refresh must put back even
    when the saved desktop never knew them — the card opened while the page was closed, or another browser did
    the work. Best-effort by construction: an empty list means «I don't know», and the restore falls back to the saved
    desktop alone."""
    out: list = []
    try:
        from nucleo import dispatch as _d
        from nucleo import sheets as _sh
        from widgets.results import data as _rd
        for r in _d._sheet_sessions():
            sid = _sh.sheet_of(r)
            if sid:
                out.append(_rd.instance_id(sid))
    except Exception:  # noqa: BLE001
        pass
    try:
        from widgets.navegador import tasks as _t
        for tid in _t.all_ids():
            out.append(_t.inst_id(tid))
    except Exception:  # noqa: BLE001
        pass
    seen: list = []
    for i in out:
        if i and i not in seen:
            seen.append(i)
    return seen


@router.post("/api/canvas/arrange")
async def canvas_arrange():
    """Aligns every open card into a grid — the OS-style window snap, invocable by API (V2-464).

    The frontend does the geometry (it is the canvas authority, V2-035); this only broadcasts the ORDER over
    the same SSE rail every other canvas command travels. Exists for the use-case recorder (a video where the
    cards land tidy without a hand on the mouse) and for anything else that can POST — the operator asked for
    it by analogy with the desktop-arrange gesture of macOS/Windows."""
    return JSONResponse(emit("widget", "arrange", extra={"src": "api"}))


@router.get("/api/canvas/layout")
async def canvas_layout():
    """The desktop AS the operator left it (cards + positions) PLUS `live`, the instance cards of errands
    running right now (V2-351). Restoration fallback when browser `localStorage` does not have it — another
    browser, another profile, or the same zaelar through another origin (localhost:43917 vs
    local.zaelar.com:44317, two distinct stores for the same desktop). Read-only."""
    live = _live_canvas_instances()
    sheets = _sheet_ids_on_disk()     # V2-773: the sheets a browser may keep — a `results::` id off this list is a ghost
    try:
        from memory import api as memory
        snap = memory.kv_get("canvas_layout")
        if isinstance(snap, dict) and isinstance(snap.get("items"), list):
            return JSONResponse({"items": _prune_ghost_sheets(snap["items"], live), "at": snap.get("at") or 0,
                                 "live": live, "sheets": sheets})
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse({"items": [], "at": 0, "live": live, "sheets": sheets})
