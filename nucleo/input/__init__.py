"""The turn's INPUT adapters (refactor2710-01): every channel hands the turn one complete `Utterance`.

A channel decides once, at its own door, when what it carries is finished. Speech is not finished when an STT final
lands — a sentence may continue in the next one — so the voice channel runs the phrase accumulator (`stt.py`). A typed
line is finished by construction: he pressed Enter (`typed.py`). Nothing downstream of an adapter asks «is it over?».

    stt.py     the phrase accumulator: fragments wait for the rest of the sentence (voice only)
    typed.py   a typed line is complete; and it waits for a spoken sentence begun before it
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

VOICE = "voice"
TYPED = "typed"


@dataclass(frozen=True)
class Utterance:
    text: str
    channel: str                       # VOICE | TYPED
    origin: str = "operator"
    device: str = ""                   # the screen that sent it; empty = the voice holder
    at: float = field(default_factory=time.time)

    @property
    def complete(self) -> bool:
        """Only speech can arrive unfinished; everything else is a whole line."""
        return self.channel != VOICE


def of_turn(text: str, *, device: str = "") -> Utterance:
    """The utterance a LiveKit turn carries. LiveKit hands typed and spoken lines to the same turn, so the channel is
    read from the typed door's own stamp (`attention.typed_line`, exact per line, read-only)."""
    try:
        from voice import attention
        typed = attention.typed_line(text)
    except Exception:  # noqa: BLE001 — without the stamp a line is treated as speech, today's behaviour
        typed = False
    return Utterance(text=text, channel=TYPED if typed else VOICE, device=device)
