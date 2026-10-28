"""voice/engine/llm/providers/vault_intercept.py — the VOICE delivery of the shared vault gate.

Born in V2-112 as the first slice extracted from `_run_inner`, carrying the whole decision inline. F1 of the
2026-08-23 audit moved that decision to `nucleo/turn/vault_gate.py`, because the probe channel had its own copy
of it — three mirror markers — and the two had already drifted (that copy
answered with the parenthetical «(secreto cifrado)» where this one says a real localized sentence, and V2-141
had to be fixed in both places separately).

What is left here is what is genuinely voice's: SPEAKING the line through `_run_inner`'s closure and emitting
the observability rows. `send`/`emit` stay explicit parameters rather than fresh imports — `send` closes over
turn state (spoken/first_ms/brain._last_spoken/_last_reply, see nucleo.py) and `emit` may have been locally
overridden to a no-op on some error paths; passing the live callables preserves behavior exactly.

`try_vault_intercept()` keeps its contract byte for byte: `(handled, text)`, where `handled` True means the turn
was fully consumed (the caller must `return` immediately) and `text` is the ORIGINAL when nothing applied, the
REDACTED one once a secret was seen. The value never survives into that text either way.
"""
from __future__ import annotations

from voice import speech


async def try_vault_intercept(text: str, first_turn: bool, send, emit) -> tuple[bool, str]:
    from nucleo.turn import vault_gate

    # The kickoff greeting is not the operator talking, so neither intercept applies to it — that is a fact
    # about the TURN, which is why the gate takes it as `enabled` rather than asking which channel is calling.
    v = await vault_gate.inspect(text, enabled=not first_turn, store=True)

    if v.kind == "config":
        emit("secret", "config", role="system", extra={"key": v.config[0], "value": v.config[1]})
        send(speech.sanitize(v.line, drop_metadata=False))
        return True, ""

    if v.kind in ("saved", "carried"):
        emit("secret", "saved", role="system", extra={"n": len(v.labels), "labels": v.labels})
    elif v.kind == "need_vault":
        emit("secret", "no_vault", role="system")       # the frontend opens the create-vault modal

    if v.consumed:
        send(speech.sanitize(v.line, drop_metadata=False))
        return True, ""
    return False, v.text


async def vault_first(text: str, first_turn: bool, emit, event_ch) -> tuple[bool, str]:
    """The vault BEFORE anything reads his words (refactor2710-01): a secret said inside a request is redacted
    here, so neither the brief, the memory heart nor the prompt — nor the window after them — ever holds it (the
    voice turn used to run it after composing the prompt, and the model read the IBAN back). When the whole turn
    was the secret or a vault setting, its line is said on the turn's own channel and the turn ends."""
    lines: list = []
    done, text = await try_vault_intercept(text, first_turn, lines.append, emit)
    if done:
        from livekit.agents import utils
        from livekit.agents.llm import ChatChunk, ChoiceDelta
        for line in lines:
            event_ch.send_nowait(ChatChunk(id=utils.shortuuid(), delta=ChoiceDelta(role="assistant", content=line)))
    return done, text
