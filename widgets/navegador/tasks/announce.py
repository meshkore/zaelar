"""What a task tells the operator and hears back: a wall it hit, the page it is on, a question and its answer.
Moved out of `tasks.py`; the registry's state and every module name are read through the package (`_f.<name>`), so
a patch on `tasks` still governs every call.
"""

import time

from widgets.navegador import tasks as _f


def _announce_wall(task_id: str, reason: str) -> None:
    """A wall is not progress and it is not a phase: it is the end of what this task can do on its own.

    So it is SAID in the three places the operator can see, instead of only being a field somebody might read
    (V2-167, operator's request: «could we show the browser image on screen and say "Booking has blocked me"
    and add a screenshot of what happened and tell them that you can no longer continue»):

      · a MILESTONE, which lands in the card's feed AND in the durable event registry, so it can be audited
        later — a phase alone dies with the task;
      · the PHASE, with the spinner OFF: a spinner on a blocked page is the screen saying «trabajando» while
        nothing works, exactly the kind of state that can lie;
      · and the card is OPENED, because the capture already on disk IS the evidence — the operator sees the
        challenge page itself rather than being told about it.
    """
    _f.milestone(task_id, f"⛔ {reason} — no puedo seguir yo solo desde aquí")
    _f.set_phase(task_id, reason, False)
    # V2-571/V2-797 — the capture IS the evidence: it is raised in the errand's ONE card, never a second one.
    _f._raise_for_him(task_id, "wall")
    # …AND THE CONVERSATION, which is the one place the three above cannot reach (2026-08-20, measured on
    # `cancel-subscription-before-charge__es` and `find-theatre-tickets__es`). The card, the phase and the panel
    # are all surfaces the operator has to be LOOKING at. If he is not, the wall is recorded everywhere and said
    # nowhere: the tester measured `wall="the page asked to solve a CAPTCHA"`, `walls_hit=1` and brain-notes=0
    # in the same round the turn was still narrating that the cancellation was going ahead.
    #
    # `active_progress()` already carries the wall into the prompt, but that only helps when the operator ASKS.
    # A note is what covers the other half — it enters the NEXT turn on its own, and it does so on the TEXT
    # channel too, which `proactive.notify` cannot (its brain-note fallback lives inside `if _speaker is not
    # None`, so a chat-only session gets nothing at all).
    #
    # Same seam the FINISH of a task already uses (`owner.py`), for the same reason: a fact the operator can act
    # on has to arrive by itself.
    try:
        from voice import brain_notes
        _rec = _f.get(task_id) or {}
        _g = _rec.get("goal") or "la tarea del navegador"
        # V2-605 — the note NAMES the site and the mechanism. It already said «que entre él», and that is the
        # right offer; what it never said is HOW, so it read as a suggestion the operator should act on rather
        # than a tool the agent can fire. Measured on session `43b7bf79`: the operator offered the help himself
        # («o me abres el navegador para que yo lo vea y te confirme el captcha») and got a question about which
        # card to show, four times — `authenticate_web` was in the turn's tool list the whole time, described as
        # a LOGIN tool only. An undeclared capability is one the model narrates instead of using (V2-540).
        # The SITE matters as much as the tool: `login_site()` cannot find «thefork» in a sentence that never
        # names it, and `web_auth.start("")` deliberately opens nothing rather than guess.
        _host = str(_rec.get("url") or "").split("://", 1)[-1].split("/", 1)[0]
        _offer = (f" Si te ofrece pasarlo él («ábreme el navegador», «déjame verlo»), o si crees que su ayuda "
                  f"desatasca esto, llama a authenticate_web con site='{_host}': abre la ventana REAL en su "
                  f"ordenador para que resuelva el captcha o el login con sus manos, y la tarea sigue."
                  if _host else "")
        brain_notes.push(
            f"[SISTEMA] Navegador (tarea {task_id}): la web BLOQUEÓ «{str(_g)[:70]}» — {reason}. No va a "
            f"terminar sola. Díselo al operador EN ESTE TURNO, con una salida concreta (probar otro sitio, "
            f"que entre él, o dejarlo); no le digas que sigues con ello.{_offer}")
    except Exception:
        pass


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
            # V2-167: only a page CHANGE counts as progress. A screenshot does not: the restaurant run took ten
            # capture revisions over four URLs and spent its last eleven minutes re-photographing the same page,
            # so `shot_rev` would have reported healthy movement while nothing moved.
            if url != t.get("url"):
                t["last_progress"] = time.time()
            t["url"] = url
            was, t["wall"] = (t.get("wall") or ""), (_f.wall_reason(url) or _f.status_wall_reason(int(status or 0))
                                                     or _f.body_wall_reason(page_text))
            if t["wall"] and t["wall"] != was:
                struck = t["wall"]
                # A WALL THAT WAS STRUCK LEAVES A TRACE. `wall` above is recomputed on every capture, so it
                # describes the page the tab is standing on RIGHT NOW — and the moment the worker re-routes (which
                # is the correct thing for it to do) the fact is erased. Measured on `find-theatre-tickets__es`
                # (2026-08-20 12:39): the body-served wall detector fired in production — the judge quotes its
                # exact wording back at us, «el sitio bloqueó el acceso» — the worker adapted and moved on to
                # elcorteingles.es, and zaelar spent TEN turns saying «it still gives no indication of where it is». The
                # obstacle had happened, nobody could still see it, and the operator was never told.
                #
                # Bounded, and it keeps the SITE: «I was blocked» is a fact, «entradas.com blocked me» is one the
                # operator can act on. Same lesson as V2-150/V2-196/V2-198, now for an obstacle instead of an
                # ending: a fact that only lives one turn is a fact the conversation loses.
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
    # A QUESTION NOBODY IS ASKED IS NOT A QUESTION. Measured 2026-08-20 on `find-theatre-tickets__es`: the task
    # parked on «Voy a pulsar COMPRAR ENTRADAS. ¿Lo confirmo?» at 16:22:18 and the operator was never told —
    # the question reached the card's feed and stopped there. V2-202 gave the ANSWER a way back in
    # (`answer_from_turn`); this is the other half, the way OUT. Without it the gate stops the work and waits on
    # a person who does not know they are being waited on, which is the confirm-gate defect one layer up.
    try:
        from voice import brain_notes
        brain_notes.push(
            f"[SISTEMA] Navegador (tarea {task_id}): «{_goal[:70]}» está PARADA esperando tu OK. Pregúntaselo al "
            f"operador EN ESTE TURNO, literalmente: «{str(question or '')[:140]}». Su sí o su no ES la respuesta: "
            f"no lo trates como una petición nueva.")
    except Exception:
        pass


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

    V2-202 — until now the ONLY way to answer was the card's button (`answer_task`, a widget data-op), so a
    confirm-gate hit during a voice/text errand had no route back at all: `waiting_id()` had zero callers in
    production. Measured on `find-theatre-tickets__es` (2026-08-20 13:33): the gate stopped «Comprar entradas»,
    asked nobody, and failed the worker with `action NOT confirmed by the operator` while the turn kept
    reporting progress. The judge, reading only the dialogue, called it «waiting for a confirmation that was never
    requested from the user» — both halves of the same hole.

    The decision lives HERE, with the state it resolves, exactly like `dispatch.resolve_confirm` lives with
    `_PENDING_CONFIRM`: both channels call this one function instead of each classifying on its own (V2-153 is
    what two copies of one decision cost). The yes/no classifier is the shared deterministic one — a gate is no
    place to ask an LLM whether «come on, go ahead» meant yes.
    """
    tid = _f.waiting_id()
    if not tid:
        return None
    # ⚠️ `needs_input` does NOT mean «there is a question»: the LOGIN handoff sets it (`owner._authenticate`), and
    # the tasks that handoff PAUSES do too, both WITHOUT a question. Without this check, a turn containing a
    # «okay» —«Okay, open the Netflix website and tell me when it is at the login»— was read as the answer to a
    # confirm-gate nobody had opened, consuming that turn's REAL action. Regression measured the same day
    # in `cancel-subscription-before-charge__es`, which was the only 5/5 on the board. The question is the only thing
    # distinguishing «I am waiting for you» from «I am waiting for YOU to do something in another window».
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
