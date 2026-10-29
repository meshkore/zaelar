"""A second pass that can only CONFIRM or CORRECT words already said never holds them back (V2-831 T-19 R5b).

Demo sandbox build 86, C2 («find me a free 45 minutes tomorrow afternoon…»): the first pass had the right words at
~2 s; the words-after-data pass was told what was already said, and so could only answer SKIP or a correction. It
spent ~11 s before its first token (provider time on a ~0.7 k-token prompt) and answered SKIP — and the turn, with
its reply event, waited for it: the wall got the words at 12.7 s, after his next sentence.

The rule: when the turn already said words and a live session can take a later line, the pass runs DETACHED. The
turn closes on the words it has; a SKIP is silence, a correction is a follow-up delivered through the proactive
door (wall, voice queue, dialog). The typed channel (`voice/typed_turn.py`) answers ONE reply per request and has
no later line to give, so there the pass stays inline — the request is the unit.

Every pass, inline or detached, is measured on its own (`turn_perf.note_pass`), so the turn's slow verdict stops
blaming the first pass's prompt for time a second pass spent.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

#: The detached passes still running — held so the loop does not collect them mid-flight.
_LIVE: set = set()


async def measured(client, sys2: str, user_text: str, spec, max_tokens: int, what: str):
    """The pass's stream, unchanged, timed and sized for `turn_perf` (TTFT from the client's own metrics)."""
    m: dict = {}
    t0 = time.monotonic()
    try:
        async for delta in client.stream([{"role": "system", "content": sys2}, {"role": "user", "content": user_text}],
                                         spec=spec, max_tokens=max_tokens, metrics=m):
            yield delta
    finally:
        _note(what, t0, m, sys2, user_text, detached=False)


def _note(what: str, t0: float, m: dict, sys2: str, user_text: str, *, detached: bool) -> dict:
    from nucleo.flash import turn_perf
    from nucleo.llm.fast_client import est_tokens
    tok = m.get("prompt_tokens") or m.get("prompt_tokens_est") or est_tokens(len(sys2) + len(user_text))
    return turn_perf.note_pass(what, int((time.monotonic() - t0) * 1000), prompt_tokens=int(tok),
                               ttft_ms=m.get("ttft_ms"), detached=detached)


def detach(sys2: str, user_text: str, said: str, spec, max_tokens: int, what: str, emit) -> bool:
    """Run the confirm-or-correct pass off the turn. False (run it inline) when no live session can take a later
    line: a typed turn has lent its collector (`proactive._TURN_SPEAKER`)."""
    from voice import proactive
    if not (said or "").strip() or proactive._TURN_SPEAKER.get() is not None:
        return False
    task = asyncio.ensure_future(_run(sys2, user_text, said, spec, max_tokens, what, emit))
    _LIVE.add(task)
    task.add_done_callback(_LIVE.discard)
    emit("brain", "📤 primeras palabras entregadas — el segundo pase confirma o corrige aparte", role="system",
         text=f"{what}: {said[:120]}", extra={"cat": "flash", "pass": what})
    return True


async def _run(sys2: str, user_text: str, said: str, spec, max_tokens: int, what: str, emit) -> str:
    """The detached pass: SKIP (or a repeat of what was said) is silence; anything else is the correction, said
    as a follow-up. Returns what was delivered ("" for silence). Never raises."""
    from nucleo.flash import second_pass
    from voice.tag_protocol import strip_tags
    from nucleo.llm.fast_client import FastClient
    from voice import proactive, speech
    m: dict = {}
    t0 = time.monotonic()
    raw = ""
    try:
        async for delta in FastClient().stream(
                [{"role": "system", "content": sys2}, {"role": "user", "content": user_text}],
                spec=spec, max_tokens=max_tokens, metrics=m):
            raw += delta or ""
    except Exception as e:  # noqa: BLE001 — a failed confirmation leaves the first words standing
        logger.warning(f"{what} (detached) failed: {e!r}")
    finally:
        _note(what, t0, m, sys2, user_text, detached=True)
    text = speech.sanitize(strip_tags(raw, lambda *a, **k: None, True)[0], drop_metadata=False)
    if not text or text.upper().startswith("SKIP") or second_pass.still_held(text, said):
        emit("brain", "🤐 segundo pase: SKIP — lo ya dicho contestaba", role="system",
             text=f"{what}: {said[:120]}", extra={"cat": "flash", "detached": True})
        return ""
    proactive._TURN_SPEAKER.set(None)      # this task's own context: the turn that lent a collector is over
    emit("brain", "🩹 segundo pase: corrige lo ya dicho — llega como seguimiento", role="system",
         text=f"{what}: {text[:160]}", extra={"cat": "flash", "detached": True})
    await proactive.notify("zaelar", text, speak=True, kind="notify")
    return text
