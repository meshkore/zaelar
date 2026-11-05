"""The in-turn mouth's entry for a door that speaks while its turn is live (V2-851 F5, plan §2c).

One function, two entries. A line a door owes INSIDE a turn — an escalation refused (`acts/errand._refuse`), a
capability not there yet (`flash/capability_gap.refuse`), a rule repeated back (`flash/style_directive.write_rule`), a
list's receipt on a channel with no speaker (`fast_lane.task_list`) — is said by the turn's own mouth, after its
words, as the verdict of what the door did (`turn/reply`, identity = the turn's trace). The same line when no turn of
his is live (the door ran late, after the turn closed, or off any turn) goes out of turn through the one out-of-turn
door (`pulse/notices.notify`) with a notice key: deduped, owed if he is away. Before F5 each of them called the
speaking primitive (`voice/proactive.notify`) directly — a second mouth with no identity.

`open_for` is called by the turn when it begins, `close` when it ends (it says what is still owed); in between `say`
notes the line on the turn. A turn that never closes (cancelled) leaves at most `_MAX` open marks, oldest dropped.
"""
from __future__ import annotations

import asyncio

from loguru import logger

from nucleo.circuit import verdict as V

_OPEN: list[str] = []          # the traces whose mouth is open, oldest first
_MAX = 16
_LATE: set = set()             # out-of-turn deliveries in flight, held so the loop does not collect them


def _trace() -> str:
    try:
        from voice import trace
        return trace.current() or ""
    except Exception as e:  # noqa: BLE001
        logger.debug(f"mouth: no trace — {e!r}")
        return ""


def open_for(trace: str = "") -> None:
    """The turn on `trace` (default: the current one) has begun: its mouth speaks the doors' lines."""
    t = trace or _trace()
    if t and t not in _OPEN:
        _OPEN.append(t)
        del _OPEN[:-_MAX]


def is_open(trace: str = "") -> bool:
    t = trace or _trace()
    return bool(t) and t in _OPEN


def say(text: str, *, verdict: str = V.MET.name, door: str = "", key: str = "", title: str = "zaelar",
        **voice_kw) -> str:
    """A door's line: noted on the live turn («in»), or delivered out of turn with `key` («out», `voice_kw` riding to
    the voice leg — e.g. `opens_window` for a line that waits for his answer). "" when empty."""
    text = (text or "").strip()
    if not text:
        return ""
    if is_open():
        from nucleo.turn import reply
        reply.note(reply.Outcome(verdict, door or "door", "line", said=text))
        return "in"
    try:
        from nucleo.pulse import notices
        task = asyncio.get_running_loop().create_task(
            notices.notify(title or "zaelar", text, key=key or f"{door or 'door'}:{abs(hash(text)) % 10**8}", **voice_kw))
        _LATE.add(task)
        task.add_done_callback(_LATE.discard)
    except RuntimeError:                                    # no loop (a test, the boot): the line stays on the record
        logger.debug(f"mouth: no loop for an out-of-turn line — {text[:80]}")
    return "out"


def close(said: str, send, speech) -> str:
    """The turn ends: the lines its doors still owe are said after `said` (the verdicts `reply.after_acts` did not
    take), and its mouth closes. Returns the turn's whole text. Never raises."""
    t = _trace()
    try:
        from nucleo.turn import reply
        left = reply.taken()
        if left:
            said = reply.speak(left, said, send, speech)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"mouth: the owed lines were not said — {type(e).__name__}: {e}")
    if t in _OPEN:
        _OPEN.remove(t)
    return said
