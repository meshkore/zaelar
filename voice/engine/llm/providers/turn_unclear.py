"""The voice turn's answer to a sentence it could not read (V2-833 F7/F8, V2-851 F5).

Out of `nucleo.py::_run_inner` like the other `turn_*` blocks, so the turn grows no branch for it: `_run_inner` calls
`say_unread` once, after the stream and before the post-stream chain, and `hold_deadline_s` hands the Hold the lead-in
filler's deadline (nucleo never reaches into the motor for it). It runs no model: the deliberate second look went with
every re-run after the main stream — the turn asks, and his next sentence is a new turn.
"""
from __future__ import annotations

from loguru import logger


def hold_deadline_s(filler_audio) -> float:
    """How long the Hold may wait for a brief in flight: the lead-in filler's own deadline — the time the engine already
    treats as «he is fine without words». 0 when the channel has no filler (nothing waits)."""
    try:
        return filler_audio.delay_ms() / 1000.0 if filler_audio else 0.0
    except Exception as e:  # noqa: BLE001 — an unreadable deadline waits for nothing
        logger.debug(f"turn_unclear: the filler deadline could not be read — {e!r}")
        return 0.0


def say_unread(*, hold, marked: bool, errored: bool, window, send, emit, spoken) -> bool:
    """One line from the table when the Hold dropped the reflex words under an unreadable verdict (`hold.unread`) or the
    model called `not_understood` (`marked`) and said nothing. A turn that errored has its own line. True when said."""
    unread = getattr(hold, "unread", "")
    if not (unread or marked) or errored:
        return False
    if marked and not unread and "".join(spoken or ()).strip():
        return False                                   # the model's own words already ask him
    from nucleo.flash import unclear_turn as _unclear
    said = _unclear.line(window, "".join(spoken or ()))
    if said:
        send(said)
    emit("brain", "🤔 unreadable turn: one line asks him, no second look", role="system", text=said[:200],
         extra={"cat": "flash", "readable": unread or "marked"})
    return bool(said)
