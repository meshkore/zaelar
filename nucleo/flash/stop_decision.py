"""Is THIS turn an order to stop the errand running now? One enumerated question in the turn's brief (V2-807 T-14).

Two places decide a stop. The tool gate (`tool_executor_calls._t_stop_worker`, GUARD 2) refuses a `stop_worker` the
model chose when the operator did not order it in this turn — its real purpose is context bleed: a complaint two
turns back, dragged forward by the model, must not kill a live errand (2026-08-14). And the settle backstop
(`post_stream_settle`) stops the errand when he ordered it and the model called nothing.

Both read a WORD TABLE to know whether he ordered it, and a word table reads one phrasing. A clear stop in a word
order the table did not list («para inmediatamente esa tarea que está en marcha») was refused twice while the errand
ran on, and widening the table again (V2-585 already did once) would only add the next phrasing. The question is a
judgement about the turn, so it is asked as one: here, inside the brief the turn already pays for (N questions cost
one round trip), and only while an errand is live — with none, the answer is known.

The verdict DECIDES when it is sure (CRIT-K1): a sure «stop» licenses the model's call and repairs a turn that made
none; a sure «keep» refuses a call that is drag. With no sure verdict (brief off, in flight, unsure, or asked before
an errand existed) the grammar keeps today's path, bit for bit — it is handed IN by the caller, never re-read here.

V2-820 — two more answers, because «stop» and «keep» could not hold the two corrections a running errand gets most:

  · REPLACE («no hay que crear una app, hay que crear un documento»): he drops the errand AND names the work that
    takes its place. That is ONE act. Read as a stop it killed the app build and started nothing — he had to ask
    again three minutes later; read as «keep» it would have let the app build run. A sure `replace` stops the
    errand like a stop, and the turn's errand STARTS beside it with the stopped errand's goal carried
    (`replacement`), whether or not the model escalated.
  · STEER («no mires WhatsApp, mira el correo»): he changes what the running errand must do or where it must look.
    The errand goes on, with his words. A sure `steer` relays them to it when the model did not (`steer`), so the
    promise «le digo al proceso que se limite a tu correo» is kept by the relay and never by a card op.
"""
from __future__ import annotations

from loguru import logger

KEY = "stop_errand"

INSTRUCTIONS = (
    "A background task (an errand the assistant is working on for the operator) is running right now. What does "
    "the operator, in THIS message, do to that running task — in any wording, word order or language? Answer "
    "'stop' when he orders it stopped, cancelled or abandoned and asks for nothing in its place (a «yes» to our own "
    "offer to stop it is a stop). Answer 'replace' when he abandons it AND asks, in this message, for different work "
    "instead («not that, do this other thing»). Answer 'steer' when the task should go on but he changes what it must "
    "do, where it must look or how (its scope, source, criteria or deliverable). Answer 'keep' for anything else: a "
    "complaint or comment about something earlier, a question about the task, an unrelated new request, or an order "
    "about a card on screen, a video, music or the assistant's voice.")

#: The four answers, named once (V2-820 added `replace` and `steer`).
STOP, REPLACE, STEER, KEEP = "stop", "replace", "steer", "keep"

CHOICES = {
    STOP: "he orders the task running now to stop or be cancelled, and asks for nothing in its place",
    REPLACE: "he abandons the running task AND asks for different work in its place, in this message",
    STEER: "the running task goes on, but he corrects what it must do, where it must look or how",
    KEEP: "anything else: no order about that running task in this message",
}

def ends(v) -> bool:
    """Does this answer end the running errand? A replace stops it exactly like a stop does."""
    return v == STOP or v == REPLACE


def question(last_reply: str = "") -> dict:
    """The question. Our previous line rides with it: «yes» is a stop only after we offered to stop."""
    lr = (last_reply or "").strip()
    return {"instructions": INSTRUCTIONS + (f" [Our previous reply: {lr[:200]}]" if lr else ""),
            "criteria": dict(CHOICES)}


def verdict(brief) -> str | None:
    """One of `CHOICES` when the brief is READY and SURE about it; None otherwise. Never waits, never raises."""
    if not brief:
        return None
    try:
        from nucleo.flash import turn_brief as _tb
        choice, info = _tb.read(brief, KEY, None)
    except Exception as e:  # noqa: BLE001 — a classifier may never break a turn
        logger.debug(f"stop_decision: verdict unreadable: {e!r}")
        return None
    return choice if info is not None and choice in CHOICES else None


def ordered(brief, *, grammar: bool) -> bool:
    """Did he order the running errand to stop in this turn? The sure verdict decides; without one, the grammar
    the caller handed in. Read by the tool gate (may the model's `stop_worker` run?) and by the backstop that
    repairs a turn whose model called nothing."""
    v = verdict(brief)
    return grammar if v is None else ends(v)


def repair(brief, text: str, *, escalating: bool, grammar, acted: dict | None = None) -> list:
    """Stop the running errand for a turn that ordered it and whose model did not call `stop_worker`.

    A SURE stop verdict repairs the turn whatever the model did instead — an escalation it started still starts
    («para eso y búscame otra cosa» is both). With no sure verdict, today's path: only a turn that started no
    escalation, read by the grammar (`grammar`, a callable so a sure verdict never pays for it). Returns the ids
    of the tasks it cancelled ([] when it stopped nothing). The caller only calls this when the model did not stop.
    """
    v = verdict(brief)
    if v is None and escalating:
        return []
    from nucleo import dispatch as _dispatch
    if not _dispatch.has_active():
        return []
    if not (ends(v) if v is not None else bool(grammar())):
        return []
    if acted is not None and v == "replace":
        acted["stopped"] = goals_of(text)           # V2-820: read before the cancel purges the record
    return list(_dispatch.cancel_soon(text) or [])


# ── V2-820 · a replace is ONE act: stop X and start Y, with X's goal carried ─────────────────────────────────

def replaces(brief) -> bool:
    """A SURE `replace`: the turn's errand starts beside the stop. Unsure or absent → today's path."""
    return verdict(brief) == REPLACE


def goals_of(which: str) -> list[str]:
    """The goals of the errands a stop on `which` is about to end — read BEFORE the cancel purges them. Never raises."""
    try:
        from nucleo import dispatch as _dispatch
        out = []
        for tid in _dispatch.resolve_sessions(which) or []:
            rec = _dispatch.get_record(tid)
            goal = " ".join(str(getattr(rec, "goal", "") or "").split())
            if goal and goal not in out:
                out.append(goal)
        return out
    except Exception as e:  # noqa: BLE001
        logger.debug(f"stop_decision: goals of the stopped errand unreadable: {e!r}")
        return []


def replacement(text: str, goals) -> str:
    """The request of the errand that takes the stopped one's place: HIS words, and the stopped errand's goal beside
    them, so what he had already said there (which messages, how many, how long) is not lost with the cancel. His
    words of this turn rule where the two differ. "" when there is nothing to start."""
    words = " ".join(str(text or "").split())
    if not words:
        return ""
    carried = [" ".join(str(g or "").split())[:400] for g in (goals or ()) if str(g or "").strip()]
    if not carried:
        return words
    return (f"{words}\n\n(It replaces the errand he has just stopped — «{' / '.join(carried)}». What he asked there "
            "still holds unless this message changes it; what this message says wins.)")


def start_beside_the_stop(brief, escalate_req: dict, text: str, worker_acted: dict, emit=None) -> bool:
    """A sure `replace` stopped the errand this turn (the model's `stop_worker` or the backstop): make sure the turn
    carries the errand that takes its place. The model's own escalation, if it made one, keeps its words and gains the
    carried goal; otherwise his words are the request. True when the turn now carries a replacement — `turn_after` then
    lets it through beside the stop, never as a refinement of the errand being cancelled. Never raises."""
    try:
        if (worker_acted or {}).get("v") != "stop" or not replaces(brief):
            return False
        goals = list((worker_acted or {}).get("stopped") or [])
        new = replacement(str(escalate_req.get("v") or "").strip() or str(text or "").strip(), goals)
        if not new:
            return False
        escalate_req["v"], escalate_req["replaces"] = new, goals
        if emit is not None:
            emit("brain", "🔁 replace: the stopped errand's place is taken by the one he named", text=new[:200],
                 role="system", extra={"cat": "flash", "kind_diag": "replace_started", "replaces": goals})
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug(f"stop_decision: replacement not composed: {e!r}")
        return False


# ── V2-820 · a correction of the running errand reaches the errand ──────────────────────────────────────────

def steers(brief) -> bool:
    """A SURE `steer`: his words change what the running errand must do."""
    return verdict(brief) == STEER


def steer_target() -> str:
    """The ONE live errand a steer is relayed to — "" when none or several are running (a relay to the wrong worker
    is worse than today's path, which leaves it to the model)."""
    try:
        from nucleo import dispatch as _dispatch
        live = _dispatch.resolve_sessions("")
        return str(live[0]) if len(live) == 1 else ""
    except Exception as e:  # noqa: BLE001
        logger.debug(f"stop_decision: live errands unreadable: {e!r}")
        return ""


def steer(brief, text: str, *, worker_acted: dict, emit=None, escalate_req: dict | None = None) -> str:
    """Relay his correction to the running errand when the turn's verdict is a sure `steer` and the model did not
    address a worker itself. Returns the errand it reached ("" = nothing relayed). Runs BEFORE any repair pass, so a
    promise to tell the process is kept by this relay and never turned into an op on a card. Never raises."""
    try:
        words = " ".join(str(text or "").split())
        if not words or worker_acted.get("v") or not steers(brief):
            return ""
        target = steer_target()
        if not target:
            return ""
        from nucleo import dispatch as _dispatch
        if getattr(_dispatch.get_record(target), "waiting_on", ""):
            return ""                     # it is waiting on HIM: his words are its answer, a door that runs later
        _dispatch.inject_soon(target, words)
        worker_acted["v"] = "inject"
        if escalate_req is not None:      # his correction is that errand's, not a new one: the model's escalation of it
            escalate_req["v"], escalate_req["more"] = None, []
        if emit is not None:
            emit("brain", "↪️ his correction → the running errand (steer verdict)", text=f"{target}: {words}"[:160],
                 role="system", extra={"cat": "flash", "kind_diag": "steer_relayed", "task": target})
        return target
    except Exception as e:  # noqa: BLE001
        logger.debug(f"stop_decision: steer not relayed: {e!r}")
        return ""

