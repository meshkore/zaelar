"""The voice turn answers a hard interrupt by reading its own remainder rules (V2-778 F2-22, 2026-10-02).

`hard_turn.handle` lets the turn continue when a short stop is aimed at a live WORKER («para eso» → the model calls
`stop_worker`) and when the close or the stop was not the whole request («cierra todo y ábreme la agenda», V2-688).
The old text channel mapped every hard interrupt straight to `canvas:close` / `chat`; since refactor2710-01 there is
one turn, and what is left to pin is that `handle` reads the two shared functions instead of a copy.
"""
from __future__ import annotations

from nucleo.flash import hard_turn as HT


def test_the_remainder_is_the_voice_turns_own():
    """Not a copy: `handle` reads the SAME functions the rest of the engine asks."""
    import inspect
    assert "remainder(text, hard)" in inspect.getsource(HT.handle)
    assert "is_worker_stop(text, hard)" in inspect.getsource(HT.handle)
