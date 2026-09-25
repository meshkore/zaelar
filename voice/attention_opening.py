"""voice/attention_opening.py — what opened the conversation now running, so the agent can SAY it (V2-768).

Measured 2026-09-25 (session c20ffd8e): wake-word mode, the operator on the phone with somebody else. A health
alert spoken on its own opened the reply window, his «Yo no estoy hablando contigo» fell in it, and asked «¿por
qué me has interrumpido?» the agent answered «porque oí tu nombre… me activa la palabra clave» — false: nobody
had said the name. It had no way to know what opened the window, so it made up the likeliest cause.

Two writers, both at the moment a window opens from nothing: `attention_turn.judge` on a cold turn the gate
let in (the verdict's reason: `wakeword`, `unanswered_repeat`, …) and `attention.note_bot_speech` on a delivery
the agent itself armed (`addressed`, with the words it said). One reader: the wake-word prompt line in
`nucleo/flash/style_directive.py`. A module of its own because `voice/attention.py` is already past the
architecture ceiling (T502) — the ratchet's rule is to extract, never to grow it.
"""
from __future__ import annotations

import time

#: Past this the opener no longer explains the turn in front of the model: a conversation that has been going
#: five minutes is not «the one his alert opened».
TTL_S = 300.0

_state: dict = {"opened_by": None}


def note(why: str, detail: str = "", now: float | None = None) -> None:
    """Record what opened the conversation now running."""
    _state["opened_by"] = {"why": why, "detail": (detail or "").strip()[:160],
                           "at": time.time() if now is None else now}


def reset() -> None:
    _state["opened_by"] = None


def why_listening(now: float | None = None) -> str:
    """One sentence for the prompt: what opened the conversation now running. Empty when nothing recent did,
    or when the opener is one the model cannot misreport (a verdict reason with nothing to say about it)."""
    ob = _state.get("opened_by") or {}
    now = time.time() if now is None else now
    if not ob or now - float(ob.get("at") or 0) > TTL_S:
        return ""
    d = ob.get("detail") or ""
    if ob["why"] == "addressed":
        return (f"la abriste TÚ, no él: dijiste en voz alta por tu cuenta «{d}» y lo que él dijo justo después "
                f"entró como respuesta a eso. NO oíste tu nombre.")
    if ob["why"] == "wakeword":
        return f"la abrió él diciendo tu nombre: «{d}»."
    if ob["why"] == "unanswered_repeat":
        return "la abrió que él repitió varias veces sin que nadie le contestara. NO oíste tu nombre."
    return ""
