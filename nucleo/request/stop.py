"""Is THIS turn an order to stop the errand running now? One enumerated question in the turn's brief (V2-807 T-14).

The tool gate (`tool_executor_calls._t_stop_worker`) refuses a `stop_worker` he did not order this turn (a complaint
dragged forward must not kill a live errand); the settle backstop stops the errand when he ordered it and the model
called nothing. Whether he ordered it is a judgement, so it is asked in the brief the turn already pays for, only
while an errand is live — never a word table. A sure verdict DECIDES (CRIT-K1); with none, the caller's grammar keeps
today's path. V2-820 adds two answers:
  · REPLACE — he drops the errand AND names the work that takes its place: one act; it stops like a stop and the
    turn's errand starts beside it with the stopped one's goal carried (`replacement`).
  · STEER — he changes what the running errand must do or where it looks: it goes on, with his words relayed.
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
        from nucleo.turn import brief as _tb
        choice, info = _tb.read(brief, KEY, None)
    except Exception as e:  # noqa: BLE001 — a classifier may never break a turn
        logger.debug(f"stop_decision: verdict unreadable: {e!r}")
        return None
    return choice if info is not None and choice in CHOICES else None


def model_stop(brief, *, grammar: bool) -> str:
    """The MODEL called `stop_worker`: `run` · `veto` · `ask_which` (`nucleo/turn/verdicts`); no verdict → `grammar`."""
    from nucleo.turn import verdicts
    if (out := verdicts.against_the_model(brief, KEY, ends)) != verdicts.RUN:
        return out
    return verdicts.RUN if (verdict(brief) is not None or grammar) else verdicts.VETOED


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

