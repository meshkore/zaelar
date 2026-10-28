"""What the owner writes onto a live task: its phase, the login wait, milestones, status, goal, sheet, title and
results. Names are read through the package (`_f.<name>`), so a patch on `tasks` governs every call.
"""

import time

from widgets.navegador import tasks as _f


def set_phase(task_id: str, phase: str, active: bool = True) -> None:
    """Process PHASE (what the operator wants to see, not every click): 'searching...', 'collecting results',
    'investigating the best', 'ready'. `active`=True → spinner in the card. Refreshes the card."""
    with _f._lock:
        t = _f._tasks.get(task_id)
        if not t:
            return
        t["phase"] = str(phase or "")
        t["phase_active"] = bool(active)
    _f._notify(task_id)


def set_login_wait(task_id: str, on: bool, *, blocked: str = "") -> None:
    """The card waits for him to sign in in the visible window. `blocked` (V2-822, `no_window`): no window can reach
    him — a LIVE state the panel names, `needs_input` with no question (his next words are not its answer)."""
    with _f._lock:
        t = _f._tasks.get(task_id)
        if not t:
            return
        t["awaiting_login"] = bool(on)
        if blocked:
            t.update(blocked=str(blocked), status="needs_input", phase_active=False)
    _f._notify(task_id)
    if on:
        _f._raise_for_him(task_id, "login")


def _raise_for_him(task_id: str, why: str) -> None:   # he must act in the page → the errand's ONE card (V2-797)
    try:
        from nucleo import errand_card
        from voice.observer import emit
        card = errand_card.card_for(task_id, must_act=True)
        card and emit("widget", "show", extra={"id": card, "src": f"{why}:{task_id}"})
    except Exception:
        pass


def milestone(task_id: str, text: str) -> None:
    """A process MILESTONE (e.g. '34 listings found', 'analyzing 10 finalists') — NOT every browser action.

    Goes to TWO places: the card feed (ephemeral, dies with the task) and the event registry, auditable later with
    the trace of the requesting phrase and the actor `span` — what a task FOUND and DISCARDED is the evidence."""
    _f.add_event(task_id, text)
    try:
        from voice.observer import emit
        extra = {"id": "navegador", "task": task_id, "span": f"web:{task_id}"}
        tid = _f.trace_of(task_id)
        if tid:
            extra["trace"] = tid
        emit("navegador", "🏁 hito", text=str(text), extra=extra)
    except Exception:
        pass


def set_status(task_id: str, status: str) -> None:
    with _f._lock:
        t = _f._tasks.get(task_id)
        if not t or t["status"] == status:
            return
        t["status"] = status
        if status in _f.ENDED_STATES:
            # V2-197: the SAME ended-states list the filters use; a terminal state that does not record its time is
            # an ending nobody can date.
            t["finished"] = time.time()   # mark the CONTINUITY window (find_continuation)
            # …and the SPINNER goes off with it: an ended task must not keep claiming work in flight. The phase TEXT
            # is left alone on purpose — the last true thing that happened, and it dates the ending.
            t["phase_active"] = False
    _f._notify(task_id)


def set_goal(task_id: str, goal: str) -> None:
    """Update a task OBJECTIVE (operator clarifications MODIFY it). The automator loop re-reads the objective on every
    step (agent.run_task) → a clarification about a LIVE task changes what it searches without opening another
    browser. Does not touch the title (the card keeps its name)."""
    goal = (goal or "").strip()
    if not goal:
        return
    with _f._lock:
        t = _f._tasks.get(task_id)
        if not t:
            return
        t["goal"] = goal
    _f._notify(task_id)


def set_sheet(task_id: str, sheet: str) -> None:
    """Re-stamp WHOSE SHEET this tab serves (V2-571). The stamp is written at birth (V2-281), but a tab can be
    REUSED by a later errand (`find_continuation` in `_prepare_web`), and a stale stamp routes every finding to the
    predecessor's box (V2-434). Only ever overwrites with a REAL sheet: blanking would orphan findings mid-flight."""
    sheet = str(sheet or "").strip()
    if not sheet:
        return
    with _f._lock:
        t = _f._tasks.get(task_id)
        if not t or t.get("sheet") == sheet:
            return
        t["sheet"] = sheet
    _f._notify(task_id)


def set_title(task_id: str, name: str) -> None:
    """THE door for the card's header (V2-799): the errand's NAME — never a summariser's or a worker's sentence (a
    summariser's refusal of a glued brief once became the title he read)."""
    name = (name or "").strip()[:60]
    with _f._lock:
        t = _f._tasks.get(task_id)
        if not name or not t or t.get("title") == name:
            return
        t["title"] = name
    _f._notify(task_id)


def set_goal_summary(task_id: str, summary: str) -> None:
    """Set the synthesized ESSENCE of the objective (objective + criteria, compressed by LLM) as a DETAIL of the
    card — the full `goal` remains intact as operational text guiding the search. Never the title: the header is
    the errand's name (`set_title`, V2-799)."""
    summary = (summary or "").strip()
    if not summary:
        return
    with _f._lock:
        t = _f._tasks.get(task_id)
        if not t:
            return
        t["goal_summary"] = summary[:200]
    _f._notify(task_id)


def set_results(task_id: str, results) -> None:
    """Structured `results` (e.g. {"conclusion": "...", "items": [{title,subtitle,price,url,image}]})."""
    with _f._lock:
        t = _f._tasks.get(task_id)
        if not t:
            return
        t["results"] = results
    _f._notify(task_id)
