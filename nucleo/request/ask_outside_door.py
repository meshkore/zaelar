"""nucleo/request/ask_outside_door.py — a question about a door's act that the door never asked is COUNTED (V2-851 F2c).

The door is the one reader of «which person / which channel / which missing fact»: the model passes his words as he
said them, the door's consent verdict asks (ASK_WHICH / ASK_FACT), the asker makes the row wait with the act retained,
and his answer re-runs it (`nucleo/request/inline_ask`). A turn that ends on OUR OWN question while the brief names a
card whose actions leave the machine, and no call reached any door, asked outside it: nothing was retained, no
durable question exists, and his answer only works if the model happens to call the door next turn.

This is a measurement, never a repair: it emits one observer event `ask_outside_door` with the turn's trace and the
card the brief named, and nothing runs again (re-runs after the stream are 0 by design). What makes the model call
the door instead is the action's declaration (its manifest `usage`), not a sentence here.

«Our own question» is read off the reply's closing mark, or off the directory (the reply named two or more of the
people his word reaches — `nucleo/acts/message.asked_which`): never off a word list.
"""
from __future__ import annotations

#: The observer kind (family `flash`): {trace, widget, leaves, text}.
KIND = "ask_outside_door"
#: A reply that closes on one of these closes on a question. Punctuation, not vocabulary.
_QUESTION_MARKS = ("?", "？", "؟")


def ends_on_question(reply: str) -> bool:
    return str(reply or "").rstrip().rstrip("»\"'”)").endswith(_QUESTION_MARKS)


def _named_card(brief) -> str:
    try:
        from nucleo.turn import verdicts
        wid, _info = verdicts.read(brief, "catalog_widget", None)
        return "" if not wid or str(wid) == "none" else str(wid)
    except Exception:  # noqa: BLE001
        return ""


def _leaving_acts(wid: str) -> list[str]:
    try:
        from widgets import effects
        acts = (effects._manifest(wid).get("actions") or {})
        return sorted(a for a in acts if effects.leaves(wid, a))
    except Exception:  # noqa: BLE001
        return []


def measure(brief, reply: str, *, did_act: bool, asked_which: bool = False, emit=None) -> bool:
    """Emit `ask_outside_door` when this turn asked about a door's act without reaching the door. True if emitted."""
    if did_act or not (asked_which or ends_on_question(reply)):
        return False
    wid = _named_card(brief)
    leaves = _leaving_acts(wid) if wid else []
    if not leaves:
        return False
    try:
        trace = ""
        from voice import trace as _trace
        trace = str(_trace.current() or "")
    except Exception:  # noqa: BLE001
        pass
    extra = {"trace": trace, "widget": wid, "leaves": leaves, "which_person": bool(asked_which)}
    try:
        if emit is None:
            from voice.observer import emit as _emit
            emit = _emit
        emit(KIND, "🚪 asked outside the door", text=str(reply or "")[:300], role="system", extra=extra)
        return True
    except Exception:  # noqa: BLE001
        return False
