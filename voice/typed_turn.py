"""The voice motor's front door for a TYPED line (refactor2710-01): its own turn, run without LiveKit.

`nucleo/cli/turn.py` — the typed channel, the decision bank, the HTTP face — hands a line here and gets back what
the turn said. The turn is `NucleoLLMStream`'s own (`_run`, `_run_inner` and the two methods they call), borrowed
whole, with its two seams filled: the context holds his line, a collector takes what it says. Living inside
`voice/`, it is the one place outside the stream class that knows the motor's internals.
"""
from __future__ import annotations


def new_brain():
    """A fresh per-conversation brain (window, seeded flag, style directive), as the LiveKit session holds one."""
    from voice.engine.llm.providers.nucleo import NucleoLLM
    return NucleoLLM()


class _TypedTurn:
    """The voice turn, borrowed whole from the LiveKit stream — `_run`, `_run_inner` and the two methods they call —
    with its two seams filled by the typed channel: the context holds HIS line, the channel collects what the turn
    says. No `LLMStream` underneath, so no task of its own and no retry that would re-run the turn's doors."""

    def __init__(self, brain, text: str):
        from types import SimpleNamespace
        from voice.engine.llm.providers.nucleo import NucleoLLMStream
        self._llm = brain
        self._chat_ctx = SimpleNamespace(items=[SimpleNamespace(role="user", text_content=text)])
        self._said: list[str] = []
        self._event_ch = SimpleNamespace(send_nowait=lambda chunk: self._said.append(
            getattr(getattr(chunk, "delta", None), "content", None) or ""))
        for name in ("_run", "_run_inner", "_superseded", "_note_death"):
            setattr(self, name, getattr(NucleoLLMStream, name).__get__(self))


async def drive(brain, text: str) -> str:
    """The turn, with its out-of-band speaker lent to the reply: what a lane says through `proactive.speaker()` (the
    action map's ack, a rename's confirmation) is what this channel answers, never a line on a live session."""
    from voice import proactive
    turn = _TypedTurn(brain, text)

    def _say(line: str, *_a, **_k) -> None:     # synchronous: a lane may fire its speaker without awaiting it
        if line:
            turn._said.append((" " if turn._said else "") + str(line))
    token = proactive._TURN_SPEAKER.set(_say)
    try:
        await turn._run()
    finally:
        proactive._TURN_SPEAKER.reset(token)
    return "".join(turn._said).strip()
