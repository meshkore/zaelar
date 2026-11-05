"""The second pass's seams of a kept promise (V2-831 audit A10b): the `cannot_do` tool it may answer, what it records
into the turn's outcome, whether its repaired call landed, and the card it asks about when no verdict named one. The
honest line that once read these records is gone (V2-851 F1): the turn's one line is the mouth's verdict
(`nucleo/turn/reply.py`). This module goes in F2 with the promise repair."""
from __future__ import annotations

from loguru import logger as _log

#: The pass's outcomes, as `outcome["kind"]` records them.
CALL, JUDGED, SWALLOWED, CANNOT = "call", "judged", "swallowed", "cannot"
HELD = "held"            # the pass's call would write what the data already holds: met, nothing ran, nothing owed


def _base(wid) -> str:
    return str(wid or "").split("::", 1)[0].strip().lower()


def verdict_missing(brief) -> bool:
    """The decision model gave this turn NOTHING to read: no brief, one still in flight, or one whose every answer
    failed (an error, or confidence 0). An UNSURE verdict is not missing — it is the model's own path."""
    try:
        from nucleo import jev as _jev
        v = _jev.peek(brief)
        if not v:
            return True
        answers = [a for a in v.values() if isinstance(a, dict)] if isinstance(v, dict) else []
        return not answers or all(str(a.get("error") or "").strip() or not float(a.get("confidence") or 0.0)
                                  for a in answers)
    except Exception:  # noqa: BLE001
        return True


def unrun_model_card(model_calls, ran_ops) -> str:
    """The card of the last `widget_data` call the MODEL made this turn that did not run (a guard's discard does not
    make its card unknown) — "" when none."""
    ran = {(_base(w), str(a or "")) for w, a in (ran_ops or ()) if w}
    for c in reversed(list(model_calls or ())):
        if not isinstance(c, dict) or c.get("name") != "widget_data":
            continue
        args = c.get("args") if isinstance(c.get("args"), dict) else {}
        wid, act = _base(args.get("widget_id")), str(args.get("action") or "")
        if wid and (wid, act) not in ran:
            return wid
    return ""


def write_kept_unrun(model_calls, data_done) -> str:
    """The card of a WRITE the model called that a veto kept unrun, in a turn where no data-op ran — "" otherwise.

    V2-845: a veto that dropped the write or showed the card instead set `acted`, so the promise doors read the turn as
    acted and «I'll put it in your agenda» stood over an empty agenda. A vetoed write is not the act his words owed: the
    doors read it as not acted, and the second pass (or the honest line) settles the promise. Never raises."""
    try:
        if (data_done or {}).get("v"):
            return ""
        from widgets import effects
        ran = {(_base(w), str(a or "")) for w, a in ((data_done or {}).get("ops") or ()) if w}
        for c in reversed(list(model_calls or ())):
            if not isinstance(c, dict) or c.get("name") != "widget_data":
                continue
            args = c.get("args") if isinstance(c.get("args"), dict) else {}
            wid, act = str(args.get("widget_id") or ""), str(args.get("action") or "")
            if wid and (_base(wid), act) not in ran and effects.carries(wid, act, effects.DATA_WRITE):
                return _base(wid)
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_repair: kept-unrun write unreadable: {_e!r}")
    return ""


def card_for_the_repair(brief, *, model_calls=(), ran_ops=(), open_ids=None) -> str:
    """The card the promise repair asks about when no verdict named one. Never raises; "" = no card."""
    try:
        card = unrun_model_card(model_calls, ran_ops)
        if card or not verdict_missing(brief):
            return card
        if open_ids is None:
            from nucleo.flash import canvas_visibility as _cv
            open_ids = _cv.open_ids()
        ids = sorted({_base(i) for i in (open_ids or ()) if _base(i)})
        from nucleo import canvas_focus as _focus
        return _base(_focus.last_turn_card(ids)) or (ids[0] if len(ids) == 1 else "")
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_repair: line 96 failed: {_e!r}")
        return ""


#: The non-acting tool the second pass is offered beside `widget_data` (`act_repair.call_for_promise`).
CANNOT_TOOL = {
    "type": "function",
    "function": {
        "name": "cannot_do",
        "description": ("You promised or claimed an act on the card and did NOT do it: give the reason — no_action (none of "
                        "its declared actions does it), missing_detail (one does, a detail is missing), awaits_his_yes (your "
                        "reply already asks him). The engine says it in his language; you write no sentence."),
        "parameters": {"type": "object", "required": ["reason"], "properties": {"reason": {
            "type": "string", "enum": ["no_action", "missing_detail", "awaits_his_yes"]}}},
    },
}


#: The sentence the second pass's prompt gains when it may answer `cannot_do` (`act_repair.call_for_promise`).
_CANNOT_LINE = (" If you promised or claimed an act on «{wid}» and did not do it, call `cannot_do` instead with its "
                "declared reason.")


def offer_line(outcome: dict | None) -> str:
    return _CANNOT_LINE if outcome is not None else ""


def offer_tools(outcome: dict | None) -> list:
    """The extra tool the pass is offered — none unless the caller owns an outcome. Opens the record as JUDGED."""
    if outcome is not None:
        outcome["kind"] = JUDGED
    return [CANNOT_TOOL] if outcome is not None else []


def took(outcome: dict | None, name: str, args) -> bool:
    """True when the pass's call was its `cannot_do` (recorded, never a widget call)."""
    if outcome is None or name != "cannot_do":
        return False
    outcome.update(kind=CANNOT, reason=str((args or {}).get("reason") or "no_action").strip()[:40])
    return True


def already_holds(outcome: dict | None, wid: str, action: str, payload) -> bool:
    """The repair's call would write what the card ALREADY holds: the action's declared end state, rendered over this
    payload, reads met against the data now (V2-831 T-19 pass 9, INIT «Pixel — veterinarian»: the row existed, the
    pass had no way to say so and declared a missing detail). Then nothing runs and nothing is owed. Never raises."""
    try:
        from nucleo.circuit import spec as _spec, verify as _verify
        dw = _spec.render(wid, action, payload)
        if not dw or _verify.check(dw) is not True:
            return False
    except Exception as _e:  # noqa: BLE001 — unreadable: the call runs as before
        _log.debug(f"promise_repair: end state unreadable: {_e!r}")
        return False
    if outcome is not None:
        outcome["kind"] = HELD
    __import__("voice.observer", fromlist=["emit"]).emit(
        "brain", "✅ the order is already met by the card's data — nothing written", role="system",
        text=f"{wid}:{action}", extra={"cat": "flash", "kind_diag": "repair_already_held", "widget": wid, "action": action})
    return True


def called(outcome: dict | None, call):
    """Record that the pass produced a call (passes it through)."""
    if call and outcome is not None:
        outcome["kind"] = CALL
    return call


def card_and_outcome(card: str, brief, brain, data_done: dict) -> tuple[str, dict]:
    """The voice door: the verdict's card or the fallback one, and the turn's outcome record (`data_done`)."""
    return (card or card_for_the_repair(brief, model_calls=getattr(brain, "_turn_calls", None),
                                        ran_ops=data_done.get("ops")), data_done.setdefault("promise", {}))


def landed(call, outcome: dict, *, run, acted: dict, data_done: dict, escalate_req: dict, emit):
    """Run the repaired call; the call when it RAN (or asked, or became a worker), None when a guard swallowed it —
    then the outcome says so and the turn end owes the honest line instead of a claim."""
    if not call:
        return None
    before = bool(acted.get("widget"))     # a vetoed write already counted (V2-845): only what the pass does now lands
    run()
    if (acted.get("widget") and not before) or data_done.get("v") or escalate_req.get("v") is not None:
        return call
    outcome["kind"] = SWALLOWED
    try:
        emit("brain", "🛡️ la segunda pasada no llegó a ejecutarse — no se da por hecho",
             text=f"{call.get('widget_id')}:{call.get('action')}", role="system",
             extra={"cat": "flash", "widget": call.get("widget_id"), "action": call.get("action")})
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_repair: line 217 failed: {_e!r}")
    return None
