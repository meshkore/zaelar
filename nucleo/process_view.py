"""nucleo/process_view.py — what a RUNNING process is doing, read for the processes panel (V2-822).

The operator (2026-10-27): the work of an errand happens in the background, the card he asked for is the only one
that opens, and its progress lives in ONE place — the running process's entry in the processes panel, collapsed
(three or four lines: the step it is on, its plan ✓ ▸ ·, its latest line) or expanded by him (the whole narration,
the page the browser is on, its capture, how much it has looked at). The results sheet's «Proceso» tab and the
document's process view, which told the same story inside the deliverable, are gone.

ONE source, not a copy: everything here is DERIVED from the dispatcher's live record on every read — the same record
the sheets read (`sheets.browser_for`, `sheets.harvest_for`) and the board merges (`tasks.board`). Nothing is
stored, so a finished errand answers `alive: False` and its entry leaves the «en curso» list with it.

Keyed by EITHER id a live row carries: the per-process `task_id` every SSE `task` event names, or the durable `uid`
of its row in `tasks` (a relayed errand serves the same uid).
"""
from __future__ import annotations

from nucleo import sheets


def of(key: str) -> dict:
    """The process of the live errand named by `key`, or `{"alive": False}` when no live errand carries it."""
    k = str(key or "").strip()
    if not k:
        return {"alive": False}
    from nucleo import dispatch as _d
    for r in list(_d._SESSIONS.values()):
        if r.status not in _d.LIVE_SESSION_STATES:
            continue
        if k not in (str(getattr(r, "task_id", "") or ""), str(getattr(r, "uid", "") or "")):
            continue
        plan = [str(s) for s in (getattr(r, "plan", None) or []) if str(s or "").strip()]
        return {
            "alive": True,
            "id": str(getattr(r, "task_id", "") or ""),
            "uid": str(getattr(r, "uid", "") or ""),
            "title": sheets.title_of(r),
            "surface": str(getattr(r, "surface", "") or ""),
            "phase": str(getattr(r, "phase", "") or ""),
            "plan": plan,
            "done": max(0, min(int(getattr(r, "done", 0) or 0), len(plan))),
            "phases": sheets._phrases(r)[-sheets.PHASES_KEPT:],
            "waiting_on": str(getattr(r, "waiting_on", "") or ""),
            "ask": str(getattr(r, "ask", "") or "")[:200],
            "browser": sheets.browser_for([r]),
            "harvest": sheets.harvest_for([r]),
        }
    return {"alive": False}


def notify_for_tab(nav_task: str) -> None:
    """A browser tab changed (its page, its capture, a wall): tell the panel, if an errand drives that tab.

    The tab is named after its browser task or after its errand (the same two-name rule as
    `sheets.sheet_for_nav_task`). Never raises — a missed notice costs one stale frame."""
    tid = str(nav_task or "").strip()
    if not tid:
        return
    try:
        from nucleo import dispatch as _d
        for r in list(_d._SESSIONS.values()):
            if r.status in _d.LIVE_SESSION_STATES and tid in (str(getattr(r, "nav_task", "") or ""),
                                                             str(getattr(r, "task_id", "") or "")):
                sheets.notify_process(r)
                return
    except Exception as e:  # noqa: BLE001
        __import__("logging").getLogger(__name__).debug("process notice for tab %s failed: %s", tid, e)
