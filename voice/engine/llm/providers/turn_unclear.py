"""The voice turn's deliberate look (V2-833 F7/F8): the turn the brief read as UNREADABLE, or the model said so.

Out of `nucleo.py::_run_inner` like the other `turn_*` blocks, so the turn grows no branch for it: `_run_inner` calls
`look_again` once, after the stream and before the post-stream chain spends the turn's calls, and `hold_deadline_s`
hands the Hold the lead-in filler's deadline (nucleo never reaches into the motor for it).
"""
from __future__ import annotations

import time


def hold_deadline_s(filler_audio) -> float:
    """How long the Hold may wait for a brief in flight: the lead-in filler's own deadline — the time the engine already
    treats as «he is fine without words». 0 when the channel has no filler (nothing waits)."""
    try:
        return filler_audio.delay_ms() / 1000.0 if filler_audio else 0.0
    except Exception:  # noqa: BLE001 — an unreadable deadline waits for nothing
        return 0.0


async def look_again(*, hold, marked: bool, errored: bool, brain, messages, spec, catalog, on_tool_call, send, take,
                     buf_reset, buf_add, emit, speech, FastClient, spoken, heard: str, filler_audio, t0: float) -> None:
    """One deliberate look, one door (`nucleo/flash/unclear_turn.answer`), when the Hold dropped the reflex words under an
    unreadable verdict (`hold.unread`) or the model called `not_understood` (`marked`). A turn that errored is not read
    again. The system notes the dropped reflex turn carried are re-queued: the pass reads his words alone."""
    unread = getattr(hold, "unread", "")
    if not (unread or marked) or errored:
        return
    from nucleo.flash import unclear_turn as _unclear
    from voice import brain_notes as _bnotes
    if unread:
        for n in getattr(brain, "_turn_notes", None) or ():
            _bnotes.push(n)
    filler = filler_audio.played_recently(time.time() - t0 + 1.0) if filler_audio else ""
    await _unclear.answer(messages=messages, spec=spec, catalog=catalog, on_tool_call=on_tool_call, send=send, take=take,
                          buf_reset=buf_reset, buf_add=buf_add, emit=emit, speech=speech, window=brain._window,
                          client_factory=FastClient, said_before="".join(spoken) or filler, readable=unread, heard=heard,
                          spoken=spoken)
