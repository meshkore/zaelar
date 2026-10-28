"""What the live state says about the fleet: active summaries, the progress of each task, what just finished.
Names are read through the package (`_f.<name>`), so a patch on `tasks` governs every call.
"""

import time

from widgets.navegador import tasks as _f


def active_summaries(limit: int = 3) -> list[tuple[str, str]]:
    """(id, objective) for tasks ACTIVE now — so brain STATE says EXPLICITLY what is in progress (not just "there are N
    tasks") and does not relaunch a search that is already running. Most recent first."""
    with _f._lock:
        act = [(tid, (t.get("goal") or "").strip())
               for tid, t in _f._tasks.items() if t.get("status") in _f.LIVE_STATES]
    return list(reversed(act))[:max(1, limit)]


def active_progress(limit: int = 3) -> list[dict]:
    """What each live browser task has ACTUALLY done: the page it is on and how many steps it has taken.

    V2-145 — the truth the task records as it drives (`url`, `events`) must reach the prompt: an empty pair is not
    a gap in our knowledge, it is the fact that nothing has happened yet, and it is what the brain has to say.
    """
    now = time.time()
    with _f._lock:
        rows = [{"id": tid,
                 "goal": (t.get("goal") or "").strip(),
                 "url": (t.get("url") or "").strip(),
                 "phase": (t.get("phase") or "").strip(),
                 "steps": len(t.get("events") or []),
                 # V2-150: the last milestone as TEXT — a step count cannot be said out loud.
                 "last_event": ((t.get("events") or [{}])[-1].get("text") or "").strip()
                                if t.get("events") else "",
                 # V2-167: `stalled_s` is time since the task last MOVED (new page or reported step), not since it
                 # started — the difference between "still working" and "stuck".
                 "stalled_s": int(max(0.0, now - float(t.get("last_progress") or t.get("created") or now))),
                 # V2-302 — the task's AGE as a fact, so the turn never calls a seconds-old task «a while» silent;
                 # alongside the real facts it grounds the wording instead of replacing them (cf. V2-145).
                 "age_s": int(max(0.0, now - float(t.get("created") or now))),
                 "wall": (t.get("wall") or ""),
                 # The obstacles this task has ALREADY hit, which `wall` cannot carry (it is recomputed per
                 # capture). Count + the last one, because that is what a sentence needs.
                 "walls_hit": len(t.get("walls") or []),
                 "last_wall": ((t.get("walls") or [{}])[-1] if t.get("walls") else {}),
                 "awaiting_login": bool(t.get("awaiting_login")),
                 # V2-202: the confirm-gate's QUESTION — the only route a live task has into the prompt.
                 "question": (t.get("question") or "").strip(),
                # V2-192: a task that HAS ALREADY BROUGHT something back outweighs any measure of being stuck.
                 "has_results": bool(t.get("results"))}
                for tid, t in _f._tasks.items() if t.get("status") in ("queued", "working", "needs_input")]
    return list(reversed(rows))[:max(1, limit)]


def recently_finished(now: float | None = None, limit: int = 3) -> list[dict]:
    """Tasks that ENDED in the last few minutes, and whether they brought anything back.

    V2-150 — the brain only sees ACTIVE tasks, so a finished one VANISHED from the state; an ending is a FACT, and
    one without results is the most useful of all (same remedy as V2-131/V2-145).
    """
    now = time.time() if now is None else now
    with _f._lock:
        rows = [{"id": tid,
                 "goal": (t.get("goal") or "").strip(),
                 "status": t.get("status") or "",
                 "url": (t.get("url") or "").strip(),
                 "has_results": bool(t.get("results")),
                 "last_event": ((t.get("events") or [{}])[-1].get("text") or "").strip()
                                if t.get("events") else "",
                 "ago_s": int(now - float(t.get("finished") or now))}
                for tid, t in _f._tasks.items()
                # V2-196: `cancelled` is an ending too (`ENDED_STATES`), never a gap between active and finished.
                if t.get("status") in _f.ENDED_STATES
                and (now - float(t.get("finished") or 0)) <= _f.JUST_FINISHED_S]
    rows.sort(key=lambda r: r["ago_s"])
    return rows[:max(1, limit)]
