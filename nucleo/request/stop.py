"""Is THIS turn an order to stop the errand running now? One enumerated question in the brief, asked only while an
errand is live (V2-807 T-14): a sure verdict DECIDES (CRIT-K1), with none the caller's grammar keeps today's path.
REPLACE stops it and starts what he named (V2-820); STEER relays his correction; STOP_ALL only when sure; SETTLED ends
it as MET — his decision answered what it was for, so the row is done with his pick (V2-831 T-29)."""
from __future__ import annotations

import time

from loguru import logger

KEY = "stop_errand"

INSTRUCTIONS = (
    "A background task (an errand the assistant is working on for the operator) is running right now. What does "
    "the operator, in THIS message, do to that running task — in any wording, word order or language? Answer "
    "'stop' when he orders it stopped, cancelled or abandoned and asks for nothing in its place (a «yes» to our own "
    "offer to stop it is a stop). Answer 'stop_all' when he orders EVERY running task stopped, not just one. Answer 'replace' when he abandons it AND asks, in this message, for different work "
    "instead («not that, do this other thing»). Answer 'steer' when the task should go on but he changes what it must "
    "do, where it must look or how (its scope, source, criteria or deliverable). Answer 'settled' when his message "
    "DECIDES what the task was for, so it has nothing left to do: he picks or accepts one of the options it found or "
    "offered, says he keeps what he already has, or says he no longer needs it because the matter is decided — a "
    "decision about its subject, not an order to stop it. Answer 'keep' for anything else: a "
    "complaint or comment about something earlier, a question about the task, an unrelated new request, or an order "
    "about a card on screen, a video, music or the assistant's voice.")

#: The answers, named once (V2-820 added `replace` and `steer`, V2-831 T-29 `settled`).
STOP, STOP_ALL, REPLACE, STEER, SETTLED, KEEP = "stop", "stop_all", "replace", "steer", "settled", "keep"

CHOICES = {
    STOP: "he orders the task running now to stop or be cancelled, and asks for nothing in its place",
    STOP_ALL: "he orders EVERY running task stopped (all of them, both), not just one",
    REPLACE: "he abandons the running task AND asks for different work in its place, in this message",
    STEER: "the running task goes on, but he corrects what it must do, where it must look or how",
    SETTLED: "he decides what the task was for (picks, accepts, keeps what he has, no longer needs it): nothing left to do",
    KEEP: "anything else: no order about that running task in this message",
}

def ends(v) -> bool:
    """Does this answer end the running errand? A replace stops it exactly like a stop does; a settle ends it as met."""
    return v in (STOP, STOP_ALL, REPLACE, SETTLED)


def settled_by(brief, text: str) -> str:
    """His words when this turn SETTLES the running errand (a sure `settled`), "" otherwise: the end is then a met goal
    with his pick on the row (`dispatch.settle_soon`), never a cancellation."""
    return " ".join(str(text or "").split()) if verdict(brief) == SETTLED else ""


def all_ordered(brief) -> bool:
    """A SURE «stop every task» (≥ `verdicts.VETO`): killing several errands is irreversible; less asks (fail-closed)."""
    from nucleo.turn import verdicts
    choice, info = verdicts.read(brief, KEY, None, min_confidence=verdicts.VETO)
    return bool(info) and choice == STOP_ALL


def question(last_reply: str = "", goals=()) -> dict:
    """The question. Our previous line rides with it («yes» is a stop only after we offered to stop), and so does what
    the running task is for: a decision can only settle a goal the question names."""
    lr = (last_reply or "").strip()
    gs = " / ".join(str(g)[:160] for g in (goals or ()) if str(g or "").strip())[:400]
    return {"instructions": INSTRUCTIONS + (f" [The running task: {gs}]" if gs else "")
            + (f" [Our previous reply: {lr[:200]}]" if lr else ""), "criteria": dict(CHOICES)}


def verdict(brief) -> str | None:
    """One of `CHOICES` when the brief is READY and SURE about it; None otherwise. Never waits, never raises. A `replace`
    ends an errand: only SURE (veto floor) and AIMED at it (`errand_target`) — a new question is a new errand (M1)."""
    try:   # no brief, no read: asking would only log an `off` read
        from nucleo.turn import brief as _tb, verdicts as _v
        choice, info = _tb.read(brief, KEY, None) if brief else (None, None)
        if choice == REPLACE and not (float((info or {}).get("confidence") or 0) >= _v.VETO and _tb.read(brief, "errand_target", "")[0] == "running_errand"):
            return None
    except Exception as e:  # noqa: BLE001 — a classifier may never break a turn
        return logger.debug(f"stop_decision: verdict unreadable: {e!r}") or None
    return choice if info is not None and choice in CHOICES else None


#: When we offered to stop (the gate's `ask_which`): the next turn may take it (refactor2710-99).
_OFFER, OFFER_TTL_S = {"at": 0.0}, 300.0


def offer_taken(brief, *, the_model_stops: bool = False) -> bool:
    """His turn TAKES our open offer: the brief reads it as his answer (not a question, comment or complaint) and the
    model's `stop_worker` or the verdict's DIRECTION points at stopping — our question is the licence, not the bar."""
    if not _OFFER["at"] or time.time() - _OFFER["at"] > OFFER_TTL_S:
        return False
    try:
        from nucleo.turn import brief as _tb, verdicts
        kind, _i = _tb.read(brief, _tb.REQUEST_KEY, "")
        choice, info = verdicts.read(brief, KEY, None, min_confidence=0.0)
        return (bool(kind) and str(kind) not in ("question", "comment", "complaint")
                and (the_model_stops or (info is not None and ends(choice))))
    except Exception as e:  # noqa: BLE001 — a classifier may never break a turn
        return logger.debug(f"stop_decision: offer unreadable: {e!r}") or False


def model_stop(brief, *, grammar: bool) -> str:
    """The MODEL called `stop_worker`: `run` · `veto` · `ask_which` (an ask is our offer); no verdict → `grammar`."""
    from nucleo.turn import verdicts
    out = verdicts.against_the_model(brief, KEY, ends)
    if out != verdicts.VETOED and offer_taken(brief, the_model_stops=True):
        out, _OFFER["at"] = verdicts.RUN, 0.0
    elif out != verdicts.RUN:
        _OFFER["at"] = time.time() if out != verdicts.VETOED else _OFFER["at"]
    if out != verdicts.RUN:
        return out
    return verdicts.RUN if (verdict(brief) is not None or grammar) else verdicts.VETOED


def repair(brief, text: str, *, escalating: bool, grammar, acted: dict | None = None, card_acts: dict | None = None) -> list:
    """Stop the errand for a turn whose model did not call `stop_worker`: a sure verdict (an escalation it started
    still starts), a taken offer, or — with neither and no escalation — the grammar. Returns the cancelled ids. A turn
    a card or lane served (`card_acts`) stops nothing, a replace included: its request was answered (V2-831 T-19)."""
    v, taken = verdict(brief), offer_taken(brief)
    _OFFER["at"] = 0.0                              # an offer is answered by the turn after it, taken or not
    from nucleo import dispatch as _dispatch
    if (v is None and escalating and not taken) or not _dispatch.has_active() \
            or not (taken or (ends(v) if v is not None else bool(grammar()))):
        return []
    if card_owns_the_turn(brief, **(card_acts or {})):
        return []
    if acted is not None and v == "replace":
        acted["stopped"] = goals_of(text)           # V2-820: read before the cancel purges the record
    if words := settled_by(brief, text):
        if acted is not None:
            acted["settled"] = True
        return list(_dispatch.settle_soon(text, words) or [])
    return list(_dispatch.cancel_soon(text) or [])


# ── V2-820 · a replace is ONE act: stop X and start Y, with X's goal carried ─────────────────────────────────
def goals_of(which: str) -> list[str]:
    """The goals of the errands a stop on `which` is about to end — read BEFORE the cancel purges them. Never raises."""
    try:
        from nucleo import dispatch as _dispatch
        goals = [" ".join(str(getattr(_dispatch.get_record(t), "goal", "") or "").split())
                 for t in _dispatch.resolve_sessions(which) or []]
        return list(dict.fromkeys(g for g in goals if g))
    except Exception as e:  # noqa: BLE001
        return logger.debug(f"stop_decision: goals of the stopped errand unreadable: {e!r}") or []


def replacement(text: str, goals) -> str:
    """The request of the errand that takes the stopped one's place: HIS words (they rule), the stopped goal beside."""
    words = " ".join(str(text or "").split())
    carried = [" ".join(str(g or "").split())[:400] for g in (goals or ()) if str(g or "").strip()]
    return words if not words or not carried else (f"{words}\n\n(It replaces the errand he has just stopped — «{' / '.join(carried)}». What he asked there "
            "still holds unless this message changes it; what this message says wins.)")


def start_beside_the_stop(brief, escalate_req: dict, text: str, worker_acted: dict, emit=None) -> bool:
    """A sure `replace` stopped the errand this turn: the turn carries the errand in its place (the model's escalation
    gains the carried goal, else his words). True when it does — `turn_after` lets it beside the stop. Never raises."""
    try:
        if (worker_acted or {}).get("v") != "stop" or verdict(brief) != REPLACE:   # a sure, aimed replace only
            return False
        goals = list((worker_acted or {}).get("stopped") or [])
        if not (new := replacement(str(escalate_req.get("v") or "").strip() or str(text or "").strip(), goals)):
            return False
        escalate_req["v"], escalate_req["replaces"] = new, goals
        if emit is not None:
            emit("brain", "🔁 replace: the stopped errand's place is taken by the one he named", text=new[:200],
                 role="system", extra={"cat": "flash", "kind_diag": "replace_started", "replaces": goals})
        return True
    except Exception as e:  # noqa: BLE001
        return logger.debug(f"stop_decision: replacement not composed: {e!r}") or False


# ── V2-820 · a correction of the running errand reaches the errand ──────────────────────────────────────────
def steer_target() -> str:
    """The ONE live errand a steer is relayed to — "" when none or several are running."""
    try:
        from nucleo import dispatch as _dispatch
        live = _dispatch.resolve_sessions("")
        return str(live[0]) if len(live) == 1 else ""
    except Exception as e:  # noqa: BLE001
        return logger.debug(f"stop_decision: live errands unreadable: {e!r}") or ""


def _last_acts() -> tuple[dict, float]:
    """(his turns' last card act, when his turns last acted on a live errand). A write to an errand's OWN sheet is the
    errand's, never a card act of his (its sheet opens in the very turn that commissions it)."""
    from nucleo import dispatch as _d, done_ops
    from voice import trace as _t
    recs = [r for r in map(_d.get_record, _d.resolve_sessions("") or []) if r is not None]
    sheets = {str(getattr(r, "sheet", "") or "").split("::")[-1].lower() for r in recs} - {""}
    errand = max([0.0, *(_t.his_turn_at(t) for r in recs for t in (r.trace_id, *(getattr(i, "trace", "") for i in r.injects or ())))])
    return done_ops.his_last(exclude=sheets), errand


def last_act_owner() -> str:
    """Who acted last for HIS turns: "card" (`done_ops.his_last`) · "errand" (its commission or his steer) · ""."""
    op, errand = _last_acts()
    card = float(op.get("at") or 0.0)
    return "" if not (card or errand) else ("card" if card > errand else "errand")


def card_owns_the_turn(brief, *, acted: dict | None = None, data_done: dict | None = None, lanes: tuple = ()) -> bool:
    """THE one rule the steer and the stop backstop read (V2-747 class, U2/U3): the turn's act is a CARD's, so the
    errand running behind it is neither steered nor stopped. A card or lane carried his words out; the verdict surely
    names a card's act (S2); or `corrects_last` reads a correction AND the last act was a card's: a correction is the
    last actor's (`last_act_owner`, a fact — that verdict never decides alone)."""
    if bool((acted or {}).get("widget")) or bool((data_done or {}).get("v")) or any((r or {}).get("v") is not None for r in lanes):
        return True
    try:
        from nucleo.flash import direct_action as _da, redo_decision as _redo, verdict_card as _vc
        if bool(_da.from_brief(brief)[1]) and _da._action_sure(brief, floor=_vc.SURE):
            return True
        return bool(corrected_card(brief))
    except Exception as e:  # noqa: BLE001 — unreadable: the errand's reading stands as before
        return logger.debug(f"stop_decision: card verdicts unreadable: {e!r}") or False


def corrected_card(brief) -> str:
    """The card he corrects (`corrects_last` at the licence AND his turns' last act was its): the repair acts there."""
    from nucleo.flash import redo_decision as _redo
    return str(_last_acts()[0].get("wid") or "") if _redo.corrects(brief) and last_act_owner() == "card" else ""


def steer(brief, text: str, *, worker_acted: dict, emit=None, escalate_req: dict | None = None,
          acted: dict | None = None, data_done: dict | None = None, lanes: tuple = ()) -> str:
    """Relay his correction to the running errand on a sure `steer` the model did not address; the errand reached or
    "". Runs BEFORE any repair pass, so a promise to tell the process is kept here. Never raises. `acted` / `data_done`
    / `lanes` are the turn's own acts: what a card owns is not the errand's (`card_owns_the_turn`, one sentence one order)."""
    try:
        words = " ".join(str(text or "").split())
        target = steer_target() if (words and not worker_acted.get("v") and verdict(brief) == STEER
                                    and not card_owns_the_turn(brief, acted=acted, data_done=data_done, lanes=lanes)) else ""
        if not target:
            return ""
        from nucleo import dispatch as _dispatch
        if getattr(_dispatch.get_record(target), "waiting_on", ""):
            return ""                     # it is waiting on HIM: his words are its answer, a door that runs later
        if not _dispatch.relay_his_words(target, words):   # the one door every route of his words crosses
            return ""
        worker_acted["v"] = "inject"
        if escalate_req is not None:      # his correction is that errand's, not a new one: the model's escalation of it
            escalate_req["v"], escalate_req["more"] = None, []
        if emit is not None:
            emit("brain", "↪️ his correction → the running errand (steer verdict)", text=f"{target}: {words}"[:160],
                 role="system", extra={"cat": "flash", "kind_diag": "steer_relayed", "task": target})
        return target
    except Exception as e:  # noqa: BLE001
        return logger.debug(f"stop_decision: steer not relayed: {e!r}") or ""

