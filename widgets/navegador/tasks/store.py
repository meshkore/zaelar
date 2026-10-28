"""A task's ROW in the registry: creating it, reading it, its event feed and tally, and how it ends.
Names are read through the package (`_f.<name>`), so a patch on `tasks` governs every call.
"""

import time

from widgets.navegador import tasks as _f


def create(goal: str, title: str = "", *, trace: str = "", sheet: str = "") -> str:
    """`trace`: pass it explicitly when the caller knows it (V2-108) — `_current_trace()` reads the AMBIENT context,
    reliable only inline in a turn, not inside a worker's execution. `title`: the errand's name (V2-799, `set_title`)."""
    goal = (goal or "").strip()
    with _f._lock:
        tid = f"t{_f._next_seq('navegador.task')}"
        _f._tasks[tid] = {
            "id": tid, "goal": goal, "goal_summary": "", "title": (title or goal)[:60] or "Tarea",
            "status": "queued", "phase": "", "phase_active": False, "events": [], "results": None,
            "question": "", "answer": "", "url": "", "page_title": "", "shot_rev": 0,
            "awaiting_login": False, "created": time.time(),
            # V2-167: when this task last MOVED (new page or milestone) and whether its page is a wall, so the brain
            # tells "no news yet" from "eleven minutes on the same page".
            "last_progress": time.time(), "wall": "",
            # V2-044: the task is born from the phrase context (or adopted session) — explicit trace wins.
            "trace": trace or _f._current_trace(),
            # V2-281 — THE ERRAND'S SHEET, stamped at birth like `trace` (a tab outlives the worker record that opened
            # it). Empty stays empty for a tab he drives by hand.
            "sheet": str(sheet or "").strip(),
        }
    return tid


def ensure(task_id: str, goal: str = "", title: str = "") -> str:
    """Create the task with a FIXED id if it does not exist, or reuse it (for SINGLETON cards like manual navigation:
    one reused card instead of a new one for each open/search → no widget proliferation)."""
    with _f._lock:
        t = _f._tasks.get(task_id)
        if t:
            if goal:
                t["goal"] = goal
            if title:
                t["title"] = title[:60]
            return task_id
        _f._tasks[task_id] = {
            "id": task_id, "goal": (goal or "").strip(), "goal_summary": "",
            "title": (title or goal or task_id)[:60] or "Tarea",
            "status": "queued", "phase": "", "phase_active": False, "events": [], "results": None,
            "question": "", "answer": "", "url": "", "page_title": "", "shot_rev": 0,
            "awaiting_login": False, "created": time.time(),
            "last_progress": time.time(), "wall": "",     # V2-167
            "trace": _f._current_trace(),     # V2-044
        }
    return task_id


def get(task_id: str) -> dict:
    with _f._lock:
        t = _f._tasks.get(task_id)
        return dict(t) if t else {}


def all_ids() -> list[str]:
    with _f._lock:
        return list(_f._tasks.keys())


def active_ids() -> list[str]:
    """Tasks that have not finished yet (for routing answers / cancelling / listing)."""
    with _f._lock:
        return [tid for tid, t in _f._tasks.items() if t["status"] in _f.LIVE_STATES]


def waiting_id() -> str | None:
    """The task waiting for an operator answer (most recent if several exist)."""
    with _f._lock:
        w = [tid for tid, t in _f._tasks.items() if t["status"] == "needs_input"]
        return w[-1] if w else None


def login_waiting_id() -> str | None:
    """The task waiting for the operator to SIGN IN in the visible window (awaiting_login). Most recent if several
    exist. Used to route the voice "I'm already in" to that task's auth_done."""
    with _f._lock:
        w = [tid for tid, t in _f._tasks.items() if t.get("awaiting_login")]
        return w[-1] if w else None


def add_event(task_id: str, text: str) -> None:
    with _f._lock:
        t = _f._tasks.get(task_id)
        if not t:
            return
        t["events"].append({"t": _f._clock(), "text": str(text)[:300]})
        del t["events"][:-_f._MAX_EVENTS]
        t["last_progress"] = time.time()          # V2-167: a reported step IS progress
    _f._notify(task_id)


def tally(task_id: str, **deltas) -> None:
    """Add to this task's harvest counters: how much was looked at, and what survived each cut.

    Every number is one the pipeline ALREADY computes (`dedupe_by_url` repeats, `by_identity` unnamed, `by_amount`
    hollow, `_hand_over` offered). Written from ONE place (`act_api._hand_over`), where all halves are in scope and
    `_HANDED` guards against counting a page twice. Unknown keys are dropped: a typo must not invent a counter.
    """
    with _f._lock:
        t = _f._tasks.get(str(task_id))
        if not t:
            return
        cur = t.setdefault("tally", {k: 0 for k in _f.TALLY_KEYS})
        for k, v in deltas.items():
            if k in _f.TALLY_KEYS:
                cur[k] = int(cur.get(k, 0)) + max(0, int(v or 0))
    _f._notify(task_id)


def is_cancelled(task_id: str) -> bool:
    with _f._lock:
        t = _f._tasks.get(task_id)
        return (not t) or t["status"] == "cancelled"


def cancel(task_id: str) -> None:
    _f.set_status(task_id, "cancelled")
    _f.add_event(task_id, "⏹ cancelada por el operador")


def finish(task_id: str, status: str, summary: str = "") -> None:
    """Close the task (done|failed) and leave the summary in the feed."""
    if summary:
        _f.add_event(task_id, summary)
    _f.set_status(task_id, status if status in ("done", "failed") else "done")
