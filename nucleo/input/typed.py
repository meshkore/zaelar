"""A typed order waits for the spoken one that began BEFORE it (2026-10-22).

Turns run in the order the operator STARTED them. A spoken sentence is not a turn until the endpointing closes it
(1.2-3 s of silence after the last word), so a message typed or pasted inside that gap reached the brain FIRST —
and then the voice turn's end-of-turn interrupted it, as LiveKit does with any reply in flight. Measured in the demo
of 2026-10-22: «ok just put that away for now while you work on it» by voice, the wallpaper request pasted a second
later; the paste's turn was cancelled, the voice turn answered both from the window and the wallpaper errand was
lost. Twice in a row.

The rule is chronological, not a priority between channels: while an utterance that began before the text is still
open (no user turn committed since its onset), the text waits; when the voice turn commits, the text is scheduled
behind it (`generate_reply` queues, it does not interrupt). Voice that starts AFTER the text is an ordinary barge-in
and is untouched. The wait is bounded: if the voice went silent and no turn is coming (noise, a fragment too short to
commit), or the cap passes, the text goes in as it always did — the worst case is today's behaviour, a few seconds later.
"""
from __future__ import annotations

import time

#: Silence after the last voiced frame past which no commit is coming any more: the endpointing's longest hold
#: (`voice/endpointing.HOLD_MAX`, 3 s) plus one second of STT/EOU latency.
SILENT_GRACE_S = 4.0
#: The longest a typed order is ever held, whatever the microphone is doing.
CAP_S = 8.0

_state = {"onset": 0.0, "end": 0.0, "speaking": False, "committed": 0.0}


def _now(now: float | None) -> float:
    return time.monotonic() if now is None else now


def note_onset(now: float | None = None) -> None:
    """VAD rising edge. Keeps the EARLIEST onset of the utterance not yet committed."""
    t = _now(now)
    if _state["onset"] <= _state["committed"]:
        _state["onset"] = t
    _state["speaking"] = True


def note_end(now: float | None = None) -> None:
    """VAD falling edge: the silence the endpointing measures starts here."""
    _state["speaking"] = False
    _state["end"] = _now(now)


def note_committed(now: float | None = None) -> None:
    """A user turn entered the conversation (a user item was added): whatever was being said is now a turn."""
    _state["committed"] = _now(now)


def voice_open(now: float | None = None) -> bool:
    """Is there an utterance that began before `now` and has not become a turn yet, and could still become one?"""
    t = _now(now)
    if _state["onset"] <= _state["committed"] or _state["onset"] > t:
        return False
    if _state["speaking"]:
        return True
    return t - _state["end"] < SILENT_GRACE_S


def must_wait(since: float, now: float | None = None) -> bool:
    """A text that arrived at `since` still waits at `now`. Only for an utterance that began BEFORE it: one begun
    while it waits is later than the text and does not jump the queue."""
    t = _now(now)
    return t - since < CAP_S and _state["onset"] <= since and voice_open(t)


def reset() -> None:
    _state.update(onset=0.0, end=0.0, speaking=False, committed=0.0)
