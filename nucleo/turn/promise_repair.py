"""The second pass's seams of a kept promise (split from `promise_kept`, V2-831 audit A10b): the `cannot_do` tool it
may answer, what it records into the turn's outcome, and whether its repaired call landed. The verdicts they record
are `promise_kept`'s vocabulary; the honest line that reads them lives there."""
from __future__ import annotations

from loguru import logger as _log

from nucleo.turn.promise_kept import CALL, JUDGED, CANNOT, HELD, SWALLOWED, card_for_the_repair  # noqa: F401

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
        _log.debug(f"promise_kept: end state unreadable: {_e!r}")
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
    run()
    if acted.get("widget") or data_done.get("v") or escalate_req.get("v") is not None:
        return call
    outcome["kind"] = SWALLOWED
    try:
        emit("brain", "🛡️ la segunda pasada no llegó a ejecutarse — no se da por hecho",
             text=f"{call.get('widget_id')}:{call.get('action')}", role="system",
             extra={"cat": "flash", "widget": call.get("widget_id"), "action": call.get("action")})
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"promise_kept: line 217 failed: {_e!r}")
    return None
