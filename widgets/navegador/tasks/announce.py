"""What a task tells the operator and hears back: a wall it hit, the page it is on, a question and its answer.
The registry's state and every name are read through the package (`_f.<name>`), so a patch on `tasks` governs
every call.
"""

import time

from widgets.navegador import tasks as _f


def _announce_wall(task_id: str, reason: str) -> None:
    """A wall is not progress and it is not a phase: it is the end of what this task can do on its own (V2-167).

    So it is SAID where the operator can see it: a MILESTONE (card feed AND the durable event registry, auditable);
    the PHASE with the spinner OFF (a spinner on a blocked page lies); and the card is OPENED, because the capture
    on disk IS the evidence.
    """
    _f.milestone(task_id, f"⛔ {reason} — no puedo seguir yo solo desde aquí")
    _f.set_phase(task_id, reason, False)
    # V2-571/V2-797 — the capture IS the evidence: it is raised in the errand's ONE card, never a second one.
    _f._raise_for_him(task_id, "wall")
    # …AND THE CONVERSATION, which those surfaces cannot reach when the operator is not LOOKING. `active_progress()`
    # only helps when he ASKS; a pushed note enters the NEXT turn on its own, on the TEXT channel too (which
    # `proactive.notify` cannot). Same seam a task's FINISH uses: a fact he can act on arrives by itself.
    try:
        from nucleo.events import task_event      # a task matter, on its task and said once (V2-851 F4)
        _rec = _f.get(task_id) or {}
        _g = _rec.get("goal") or "the browser task"
        # V2-835 — the wall belongs to whoever OWNS the errand. A worker driving this tab gets the wall in its own
        # nav result and picks another source; the conversation is only INFORMED, so two actors never decide on one
        # search. One instruction per note, and none of them is a sign-in: an anti-bot wall is not passed by logging
        # in, and a window he can use is offered by the tool catalogue only where one can reach him.
        if _driven_by_worker(task_id):
            task_event.told(f"The site blocked «{str(_g)[:70]}» — {reason}. Its worker looks for another source.",
                            key=f"nav:{task_id}:wall", waiting_for="worker", speak=False)
        else:
            task_event.told(f"The site blocked «{str(_g)[:70]}» — {reason}. It will not finish by itself: try "
                            "another site, or leave it?", key=f"nav:{task_id}:wall", goal=str(_g), ok=False)
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"navegador: the wall not told — {e!r}")


def _driven_by_worker(task_id: str) -> bool:
    """Is a live Brain Worker driving this tab (it owns the errand and reads the wall itself)?"""
    try:
        from nucleo import dispatch
        rec = dispatch.record_by_nav_task(task_id)
        return rec is not None and rec.status in dispatch.LIVE_SESSION_STATES
    except Exception as e:  # noqa: BLE001 — unknown: told as his own tab, the louder of the two notes
        _f.add_event(task_id, f"⚠️ no sé si la conduce un worker: {e}"[:160])
        return False


def update_view(task_id: str, url: str = "", page_title: str = "", shot_rev: int | None = None,
                page_text: str = "", status: int = 0) -> None:
    """This task's browser changed view (new capture) → refresh its card.

    `page_text` is what the tab is SHOWING (bounded, best-effort). It is the only input that can catch a wall served
    in the body with an ordinary URL — see `body_wall_reason`. Callers that do not hold the text simply omit it and
    get exactly the URL-only behaviour they had before.
    """
    struck = ""
    with _f._lock:
        t = _f._tasks.get(task_id)
        if not t:
            return
        if url:
            # V2-167: only a page CHANGE counts as progress — a new screenshot of the same page does not.
            if url != t.get("url"):
                t["last_progress"] = time.time()
            t["url"] = url
            was, t["wall"] = (t.get("wall") or ""), (_f.wall_reason(url) or _f.status_wall_reason(int(status or 0))
                                                     or _f.body_wall_reason(page_text))
            if t["wall"] and t["wall"] != was:
                struck = t["wall"]
                # A WALL THAT WAS STRUCK LEAVES A TRACE: `wall` above describes only the page the tab stands on NOW,
                # and is erased the moment the worker re-routes. Bounded, and it keeps the SITE: «entradas.com
                # blocked me» is a fact the operator can act on (cf. V2-150/V2-196/V2-198).
                _hist = t.setdefault("walls", [])
                _hist.append({"reason": struck, "site": _f.host_of(url), "at": time.time()})
                del _hist[:-_f._MAX_WALLS]
        if page_title:
            t["page_title"] = page_title
        if shot_rev is not None:
            t["shot_rev"] = shot_rev
    _f._notify(task_id)
    if struck:
        _f._announce_wall(task_id, struck)


def ask(task_id: str, question: str) -> None:
    """The task needs data from the operator → needs_input status + question (appears in its feed and by voice)."""
    with _f._lock:
        t = _f._tasks.get(task_id)
        if not t:
            return
        t["question"] = str(question or "").strip()
        t["answer"] = ""
        t["status"] = "needs_input"
        _goal = (t.get("goal") or "").strip()
    _f.add_event(task_id, f"❓ {question}")
    # A QUESTION NOBODY IS ASKED IS NOT A QUESTION: the way OUT for the gate's question (V2-202 gave the answer its
    # way back in, `answer_from_turn`); otherwise the gate waits on a person who does not know he is awaited.
    try:
        from nucleo.events import task_event      # the question, said once out of turn (V2-851 F4)
        task_event.told(f"«{_goal[:70]}» is stopped waiting for his OK: {str(question or '')[:140]}",
                        key=f"nav:{task_id}:ask:{abs(hash(str(question))) % 10**8}", goal=_goal, ask=True)
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"navegador: the question not told — {e!r}")


def answer(task_id: str, text: str) -> None:
    """The operator answered this task's question → the loop will pick it up (`answer` poll)."""
    with _f._lock:
        t = _f._tasks.get(task_id)
        if not t:
            return
        t["answer"] = str(text or "").strip()
        t["question"] = ""
        if t["status"] == "needs_input":
            t["status"] = "working"
    _f.add_event(task_id, f"↩︎ respuesta: {text}")


def answer_from_turn(text: str) -> dict | None:
    """The operator's yes/no IN THE CONVERSATION answers the task parked at the confirm-gate. None if there was
    nothing waiting or the turn was not an answer.

    V2-202 — a confirm-gate hit during a voice/text errand needs a route back besides the card's button. The
    decision lives HERE with the state it resolves (like `dispatch.resolve_confirm` with `_PENDING_CONFIRM`): both
    channels call this one function (V2-153). The yes/no classifier is the shared deterministic one — a gate is no
    place to ask an LLM whether «come on, go ahead» meant yes.
    """
    tid = _f.waiting_id()
    if not tid:
        return None
    # ⚠️ `needs_input` does NOT mean «there is a question»: the LOGIN handoff and the tasks it PAUSES set it too, with
    # no question — an «okay» in an unrelated turn must not answer a gate nobody opened. The question is the only
    # thing distinguishing «waiting for your answer» from «waiting for you to act in another window».
    if not (_f.get(tid) or {}).get("question"):
        return None
    from widgets import confirm as _confirm
    verdict = _confirm.classify_reply(text or "")
    if not verdict:
        return None
    _f.answer(tid, text or "")
    return {"task_id": tid, "ok": verdict == "yes"}


def take_answer(task_id: str) -> str:
    """The loop consumes the pending answer (once only)."""
    with _f._lock:
        t = _f._tasks.get(task_id)
        if not t:
            return ""
        ans = t.get("answer") or ""
        t["answer"] = ""
        return ans
