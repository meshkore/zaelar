"""Is THIS turn an order to stop the errand running now? One enumerated question in the brief, asked only while an
errand is live (V2-807 T-14): a sure verdict DECIDES (CRIT-K1), with none the caller's grammar keeps today's path.
REPLACE stops it and starts what he named (V2-820); STEER relays his correction; STOP_ALL only when sure."""
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
    "do, where it must look or how (its scope, source, criteria or deliverable). Answer 'keep' for anything else: a "
    "complaint or comment about something earlier, a question about the task, an unrelated new request, or an order "
    "about a card on screen, a video, music or the assistant's voice.")

#: The four answers, named once (V2-820 added `replace` and `steer`).
STOP, STOP_ALL, REPLACE, STEER, KEEP = "stop", "stop_all", "replace", "steer", "keep"

CHOICES = {
    STOP: "he orders the task running now to stop or be cancelled, and asks for nothing in its place",
    STOP_ALL: "he orders EVERY running task stopped (all of them, both), not just one",
    REPLACE: "he abandons the running task AND asks for different work in its place, in this message",
    STEER: "the running task goes on, but he corrects what it must do, where it must look or how",
    KEEP: "anything else: no order about that running task in this message",
}

def ends(v) -> bool:
    """Does this answer end the running errand? A replace stops it exactly like a stop does."""
    return v in (STOP, STOP_ALL, REPLACE)


def all_ordered(brief) -> bool:
    """A SURE «stop every task» (≥ `verdicts.VETO`): killing several errands is irreversible; less asks (fail-closed)."""
    from nucleo.turn import verdicts
    choice, info = verdicts.read(brief, KEY, None, min_confidence=verdicts.VETO)
    return bool(info) and choice == STOP_ALL


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
        logger.debug(f"stop_decision: offer unreadable: {e!r}")
        return False


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


def repair(brief, text: str, *, escalating: bool, grammar, acted: dict | None = None) -> list:
    """Stop the errand for a turn whose model did not call `stop_worker`: a sure verdict (an escalation it started
    still starts), a taken offer, or — with neither and no escalation — the grammar. Returns the cancelled ids."""
    v, taken = verdict(brief), offer_taken(brief)
    _OFFER["at"] = 0.0                              # an offer is answered by the turn after it, taken or not
    from nucleo import dispatch as _dispatch
    if (v is None and escalating and not taken) or not _dispatch.has_active() \
            or not (taken or (ends(v) if v is not None else bool(grammar()))):
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
        goals = [" ".join(str(getattr(_dispatch.get_record(t), "goal", "") or "").split())
                 for t in _dispatch.resolve_sessions(which) or []]
        return list(dict.fromkeys(g for g in goals if g))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"stop_decision: goals of the stopped errand unreadable: {e!r}")
        return []


def replacement(text: str, goals) -> str:
    """The request of the errand that takes the stopped one's place: HIS words (they rule), the stopped goal beside."""
    words = " ".join(str(text or "").split())
    carried = [" ".join(str(g or "").split())[:400] for g in (goals or ()) if str(g or "").strip()]
    if not words or not carried:
        return words
    return (f"{words}\n\n(It replaces the errand he has just stopped — «{' / '.join(carried)}». What he asked there "
            "still holds unless this message changes it; what this message says wins.)")


def start_beside_the_stop(brief, escalate_req: dict, text: str, worker_acted: dict, emit=None) -> bool:
    """A sure `replace` stopped the errand this turn: the turn carries the errand in its place (the model's escalation
    gains the carried goal, else his words). True when it does — `turn_after` lets it beside the stop. Never raises."""
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
    """The ONE live errand a steer is relayed to — "" when none or several are running."""
    try:
        from nucleo import dispatch as _dispatch
        live = _dispatch.resolve_sessions("")
        return str(live[0]) if len(live) == 1 else ""
    except Exception as e:  # noqa: BLE001
        logger.debug(f"stop_decision: live errands unreadable: {e!r}")
        return ""


def _names_a_cards_act(brief) -> bool:
    """The verdict SURELY names an action on a card: the sentence is that card's, not the errand's (S2 «compare them
    side by side» read results:layout 1.00 and still went to the worker as a steer)."""
    try:
        from nucleo.flash import direct_action as _da, verdict_card as _vc
        return bool(_da.from_brief(brief)[1]) and _da._action_sure(brief, floor=_vc.SURE)
    except Exception:  # noqa: BLE001 — unreadable: the steer stands as before
        return False


def steer(brief, text: str, *, worker_acted: dict, emit=None, escalate_req: dict | None = None,
          acted: dict | None = None, data_done: dict | None = None, lanes: tuple = ()) -> str:
    """Relay his correction to the running errand on a sure `steer` the model did not address; the errand reached or
    "". Runs BEFORE any repair pass, so a promise to tell the process is kept here. Never raises. `acted` / `data_done`
    are the turn's own acts: words a card already carried out are not a correction of the errand that happens to be
    running — one sentence is one order (demo sandbox 2026-10-28: the worker asked «which meeting? which image?»)."""
    try:
        words = " ".join(str(text or "").split())
        consumed = (bool((acted or {}).get("widget")) or bool((data_done or {}).get("v"))
                    or any((r or {}).get("v") is not None for r in lanes) or _names_a_cards_act(brief))
        target = steer_target() if (words and not worker_acted.get("v") and not consumed and steers(brief)) else ""
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

