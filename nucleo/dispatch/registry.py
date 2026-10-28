"""Reads of the session registry: which errands are live, what each one's sheet and progress say.
Every package name is read through `_d`, so a patch of `dispatch.<name>` reaches the code here."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nucleo.workers.session import SessionRecord

import json as _json

from nucleo import dispatch as _d


# ── proyeccion for ESTADO / prompt / /api/tasks (the sincroniza the LOOP ~1 Hz, §v2·C) ───────────────────────
def unclosed_uids() -> set[str]:
    """The durable ids of every session whose run has not reached `tasks.closed()` yet — LIVE or not: a delivered
    session waits in `_SESSIONS` to SPEAK, and reading only live states settled its row as failed (demo pass S1)."""
    return {str(getattr(r, "uid", "") or "") for r in list(_d._SESSIONS.values())} - {""}


def active_sessions(now: float | None = None) -> list[dict]:
    """Serializable snapshot of LIVE sessions only (no handles) — the source of truth for STATE and /api/tasks.
    A finished session still in `_SESSIONS` must never read as «in progress» (2026-08-18: the Processes tab painted
    finished errands as working while the flows board said none was live); what ENDED is read from `tasks`."""
    # `now` is injectable so `sync_state`'s change check can freeze the clock.
    now = _d.time.time() if now is None else now
    out = []
    for r in _d._SESSIONS.values():
        if r.status not in _d.LIVE_SESSION_STATES:
            continue
        out.append({
            "id": r.task_id, "kind": r.kind, "backend": r.backend, "goal": r.goal[:120],
            # V2-728 — the DURABLE id of the commission this session serves. `id` above is the per-process
            # session counter and is what every existing consumer keys on, so it stays; this is what joins
            # the hot detail to the row in `tasks`, and a relay carries the same one as its parent.
            "uid": str(getattr(r, "uid", "") or ""),
            # V2-530 — the NAME, beside the brief and never instead of it: `goal` still carries the
            # operator's own words (dedup compares them, observability audits them) and `title` is what a
            # human reads or hears. Falls back to the brief, so a consumer can use it unconditionally.
            "title": _d._sheets.title_of(r),
            "phase": r.phase, "status": r.status, "age_s": int(now - r.started), "paused": r.paused,
            # V2-227: where mira the operator. El frontend opens the sheet with esto ANTES of that haya a result,
            # so that viaja in the proyeccion live and no in the entrega.
            "surface": r.surface,
            # SILENCIO real from the ultimo evento of the worker. Es it that of truth says if esta stalled — `age_s`
            # only says if lleva rato trabajando, that no es it same (ver the detector in nucleo/pulse/loop.py).
            "silent_s": int(now - (r.last_event_at or r.started)),
            "waiting_on": r.waiting_on, "ask": r.ask[:160] if r.ask else "",
            # V2-059: observabilidad estructurada — plan + progreso + ultimos pasos reales.
            "plan": list(r.plan), "done": r.done, "total": len(r.plan), "pct": _d._progress_pct(r),
            "note": r.note, "steps": list(r.steps)[-6:],
            "considered": r.considered, "kept": r.kept,     # amplitud de una investigación (-1 = no aplica)
            # V2-776 D1 — how long since the worker last reported ITSELF (`hbnote`), and when it last showed any
            # sign of life. The pulse writes both into the durable row and enforces the first.
            "unreported_s": int(now - (getattr(r, "reported_at", 0.0) or r.started)),
            "reported": bool(getattr(r, "reported_at", 0.0)),
            "heartbeat_at": int(r.last_event_at or r.started),
            "reported_at": int(getattr(r, "reported_at", 0.0) or 0),
        })
    return out


def has_active() -> bool:
    return any(r.status in _d.LIVE_SESSION_STATES for r in _d._SESSIONS.values())


def sheets_have_live_work(card_ids) -> bool:
    """Is a LIVE errand delivering into one of these results cards (`results` or `results::<sheet>`)?

    Closing a sheet orphans only the errand that writes INTO it. `has_active()` answered for every worker, so
    an unrelated live errand (a Telegram follow-up watching for a reply) made «Close the results» fall through
    to the model, which then did something else (demo pass 2026-09-27, S4)."""
    live = [r for r in _d._SESSIONS.values() if r.status in _d.LIVE_SESSION_STATES]
    for cid in card_ids or ():
        sheet = str(cid or "").split("::", 1)[1] if "::" in str(cid or "") else ""
        for r in live:
            own = _d.sheet_of(r)
            if sheet and own == sheet:
                return True
            if not sheet and not own and _d.surfaces.opens_sheet(getattr(r, "surface", "")):
                return True
    return False


def pending_summaries() -> list[dict]:
    """Reemplaza `escalate.pending()` (§v3·G): tasks EN CURSO for the filler of the provider + the bloque of the prompt."""
    now = _d.time.time()
    return [{"id": r.task_id, "request": r.goal, "secs": int(now - r.started),
             "phase": r.phase, "waiting_on": r.waiting_on,
             # V2-131: SILENCE since the worker's last event, now in the PROMPT too — the brain said "still
             # running" six turns over a task that had emitted nothing.
             "silent_s": int(now - (r.last_event_at or r.started)),
             # V2-059: the FlashBrain can say the PASO real + progreso if the operator question "¿how va?".
             "pct": _d._progress_pct(r), "done": r.done, "total": len(r.plan), "note": r.note,
             # V2-354 — segundos without COMPLETAR a step of the plan (≠ `silent_s`); the porque, in `NO_STEP_SECS`.
             "no_step_s": int(now - (getattr(r, "last_step_at", 0) or r.started)),
             # Amplitud in curso: leaves al cerebro contestar «va by 30 candidatos» and, al acabar, ofrecer continue.
             "considered": r.considered, "kept": r.kept,
             "sheet": _d.sheet_of(r),     # V2-451: la hoja es del ENCARGO, y sin esto solo viajaba con navegador
             "surface": getattr(r, "surface", "")}
            for r in _d._SESSIONS.values() if r.status in _d.LIVE_SESSION_STATES]


def get_record(tid) -> "SessionRecord | None":
    return _d._SESSIONS.get(str(tid))


def record_by_nav_task(nav_tid) -> "SessionRecord | None":
    """El worker that conduce the tab of browser `nav_tid` (for sellar trace/span from the bridge hbweb,
    that corre in the loop of the server without contexto of trace). V2-048."""
    nav_tid = str(nav_tid)
    for r in _d._SESSIONS.values():
        if getattr(r, "nav_task", "") == nav_tid:
            return r
    return None


def _sheet_sessions() -> list:
    return _d._sheets.sheet_sessions(_d._SESSIONS.values(), _d.LIVE_SESSION_STATES)


def sheet_for_nav_task(nav_task: str) -> str:
    """La sheet donde entregar it that ESTA tab encuentre, abriendola if su errand aun no has (V2-290)."""
    return _d._sheets.sheet_for_delivery(nav_task, _d._SESSIONS.values(), _d.LIVE_SESSION_STATES)


def errand_goal_for_nav_task(nav_task: str) -> str:
    return _d._sheets.errand_goal_for_nav_task(nav_task, _d._SESSIONS.values())


def sheet_progress(sheet: str = "") -> dict:
    return _d._sheets.sheet_progress(sheet, _d._SESSIONS.values(), _d.LIVE_SESSION_STATES)


def task_progress(task: str = "") -> dict:
    """The live narrative of ONE errand by task_id — the documento sheet's process view (V2-644)."""
    return _d._sheets.task_progress(task, _d._SESSIONS.values(), _d.LIVE_SESSION_STATES)


def sheet_harvest(sheet: str = "") -> dict:
    """Los NÚMEROS of the sheet (V2-296). Cuerpo in `nucleo/sheets.py`; here only is le pasa the record live."""
    return _d._sheets.sheet_harvest(sheet, _d._SESSIONS.values(), _d.LIVE_SESSION_STATES)


def sheet_browser(sheet: str = "") -> dict:
    """El NAVEGADOR del encargo de esta hoja (V2-571). Cuerpo en `nucleo/sheets.py`; aquí solo el registro vivo."""
    return _d._sheets.sheet_browser(sheet, _d._SESSIONS.values(), _d.LIVE_SESSION_STATES)


def record_phase(tid, phase: str) -> bool:
    """Apunta a linea in the diario of PROCESO of `tid`. El body lives in `nucleo/sheets.py` (V2-281):
    here only is resuelve the record, that es it only that this module has and aquel no."""
    return _d._sheets.record_phase(_d._SESSIONS.get(str(tid)), phase, _d.PHASES_KEPT)


def sync_state() -> None:
    """Proyecta the record RAM al ESTADO of memory (`activity` + `sessions`). La calls the LOOP (~1 Hz) and the
    points of cambio grueso (start/end/cancel) — coalescada, never by-evento (§v2·C: no floodear SQLite).
    SKIP-IF-UNCHANGED (2026-07-16): the loop the calls each tick; if no there is workers live, escribia the state —and
    disparaba `memory.updated`→SSE— CADA SEGUNDO without cambio, floodeando the visor/log and churneando SQLite. Ahora
    only writes when the proyeccion REALMENTE cambia."""
    try:
        from memory import api as memory
        sess = _d.active_sessions()
        labels = [(r.phase or _d._default_label(r.kind)) for r in _d._SESSIONS.values()
                  if r.status in _d.LIVE_SESSION_STATES]
        # The CHANGE key is the projection with the clock FROZEN, so no field computed from `now` (`age_s`,
        # `unreported_s`…) can rewrite the state every tick (V2-789; a hand-kept list of such keys missed one).
        # What is WRITTEN keeps the real ages: the prompt reads them.
        stable = _d.active_sessions(now=0.0)
        snap = (tuple(labels), _json.dumps(stable, sort_keys=True, default=str))
        if snap == _d._last_sync:
            return                      # nada relevante cambió → no reescribir ni emitir memory.updated (~1 Hz)
        _d._last_sync = snap
        memory.set_state({"activity": labels, "sessions": sess})
        # REHYDRATION (2026-08-12): the same change leaves a timestamped DURABLE trace in `sys_kv`, so the next
        # start knows what was in flight (a restart killed a search without a trace). See `nucleo/rehydrate.py`.
        try:
            from nucleo import rehydrate as _rehydrate
            _rehydrate.remember(sess)
        except Exception:
            pass
    except Exception:
        pass
