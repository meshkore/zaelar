"""What the live state says about the fleet: active summaries, the progress of each task, what just finished.
Moved out of `tasks.py`; the registry's state and every module name are read through the package (`_f.<name>`), so
a patch on `tasks` still governs every call.
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

    V2-145 — the brain was told a browser task existed and its goal, and nothing else, so «how is it going?» had
    only the elapsed seconds to answer with. It turned them into detail it could not have: «it has been open on
    the page for about 2 minutes» and «still interacting», while the mechanism report for that very task read
    `status=working url= events=[] n_search_events=0` — the task had opened nothing at all.

    Same remedy as `silent_s` in V2-131, one layer down: the truth already existed here and simply never reached
    the prompt. `url` and `events` are what the task itself records as it drives, so an empty pair is not a gap
    in our knowledge — it is the fact that nothing has happened yet, and it is what the brain has to say.
    """
    now = time.time()
    with _f._lock:
        rows = [{"id": tid,
                 "goal": (t.get("goal") or "").strip(),
                 "url": (t.get("url") or "").strip(),
                 "phase": (t.get("phase") or "").strip(),
                 "steps": len(t.get("events") or []),
                 # V2-150: the run discovered «Casa Lucio only accepts reservations by phone» and the operator
                 # only heard it at the very end, when he asked to stop. The milestone was in the task all
                 # along; what the brain saw was a step COUNT. A number cannot be said out loud.
                 "last_event": ((t.get("events") or [{}])[-1].get("text") or "").strip()
                                if t.get("events") else "",
                 # V2-167: the two facts the brain was missing. `stalled_s` is time since the task last MOVED
                 # (new page or reported step), not time since it started — the difference between "still
                 # working" and "stuck" is exactly this, and without it the turn could only offer elapsed
                 # seconds, which V2-145 already established is not a description of anything.
                 "stalled_s": int(max(0.0, now - float(t.get("last_progress") or t.get("created") or now))),
                 # V2-302 — the task's AGE, as a fact. Measured on round 29 (2026-08-24 23:07): at 21 seconds
                 # of task life the turn said «it has not reported anything for a while… would you prefer that I stop it?» —
                 # offering to kill a task that had barely spawned, and priming the operator to abort (which
                 # he did). The model had no age fact, so it filled the hole with «a while». This is NOT the
                 # V2-145 regression: that incident was the brain having ONLY seconds and inventing detail
                 # from them; age alongside the real facts grounds the wording instead of replacing it.
                 "age_s": int(max(0.0, now - float(t.get("created") or now))),
                 "wall": (t.get("wall") or ""),
                 # The obstacles this task has ALREADY hit, which `wall` cannot carry (it is recomputed per
                 # capture). Count + the last one, because that is what a sentence needs.
                 "walls_hit": len(t.get("walls") or []),
                 "last_wall": ((t.get("walls") or [{}])[-1] if t.get("walls") else {}),
                 "awaiting_login": bool(t.get("awaiting_login")),
                 # V2-202: the confirm-gate's QUESTION. `ask()` has always written it here, and this is the only
                 # route a live task has into the prompt, so a task parked on «shall I press Buy tickets?» was
                 # structurally unable to reach the conversation: the operator was never asked, the answer had
                 # nowhere to arrive, and the gate died on its timeout while the turn narrated progress.
                 "question": (t.get("question") or "").strip(),
                # V2-192: if the task HAS ALREADY BROUGHT something back, that outweighs any measure of being
                # stuck. Without this field the turn could choose only between «it is still alive» and «it is
                # blocked», and neither is true when the results are there.
                 "has_results": bool(t.get("results"))}
                for tid, t in _f._tasks.items() if t.get("status") in ("queued", "working", "needs_input")]
    return list(reversed(rows))[:max(1, limit)]


def recently_finished(now: float | None = None, limit: int = 3) -> list[dict]:
    """Tasks that ENDED in the last few minutes, and whether they brought anything back.

    V2-150 — `restaurant-tonight-madrid`: the mechanism report read `status=done url=` and zaelar kept saying
    «the processes are still running — they have been running for almost 5 minutes». That is not the model inventing for the sake of it:
    the brain only ever sees ACTIVE tasks (`active_summaries`/`active_progress`), so the moment this one
    finished it simply VANISHED from the state. There was no fact left saying it had ended, let alone that it
    had ended empty — and the turn filled the hole with the only thing it still had, the worker.

    Same remedy as `silent_s` (V2-131) and the browser progress (V2-145), one step further: an ending is a
    FACT, and a task that finished without results is the most useful fact of the three.
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
                # V2-196: `cancelled` is also an ending, and it was the only one that fell into a GAP — neither
                # active (`active_summaries` filters for queued/working/needs_input) nor recently finished. So
                # the state did not mention it AT ALL and the model continued with what it last remembered:
                # «infinite wait loop on a task that had already failed», measured in `find-theatre-tickets__es`
                # (2026-08-20 03:11) con `status=cancelled` en el informe de mecanismo.
                if t.get("status") in _f.ENDED_STATES
                and (now - float(t.get("finished") or 0)) <= _f.JUST_FINISHED_S]
    rows.sort(key=lambda r: r["ago_s"])
    return rows[:max(1, limit)]
