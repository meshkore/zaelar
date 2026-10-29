"""A second pass that can only CONFIRM or CORRECT words already said never holds them back (V2-831 T-19 R5b).

Demo build 86, C2: the first pass had the right words at ~2 s; the words-after-data pass, told what was said, could
only answer SKIP or a correction, spent ~11 s before its first token and said SKIP — and the turn waited for it.
With words already out and a live session to take a later line, the pass runs DETACHED: SKIP is silence, a
correction is a follow-up through the proactive door. The typed channel (`voice/typed_turn.py`) answers one reply
per request, so there it stays inline. Every pass is measured on its own (`turn_perf.note_pass`).
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

_LIVE: set = set()        # the detached passes in flight, held so the loop does not collect them


def _messages(sys2: str, user_text: str) -> list[dict]:
    return [{"role": "system", "content": sys2}, {"role": "user", "content": user_text}]


def _note(what: str, t0: float, m: dict, n_chars: int, detached: bool) -> dict:
    from nucleo.flash import turn_perf
    from nucleo.llm.fast_client import est_tokens
    return turn_perf.note_pass(what, int((time.monotonic() - t0) * 1000), detached=detached, ttft_ms=m.get("ttft_ms"),
                               prompt_tokens=int(m.get("prompt_tokens") or est_tokens(n_chars)))


async def measured(client, sys2: str, user_text: str, spec, max_tokens: int, what: str):
    """The inline pass's stream, unchanged, noted for the turn's verdict."""
    m, t0 = {}, time.monotonic()
    try:
        async for delta in client.stream(_messages(sys2, user_text), spec=spec, max_tokens=max_tokens, metrics=m):
            yield delta
    finally:
        _note(what, t0, m, len(sys2) + len(user_text), False)


def detach(sys2: str, user_text: str, said: str, spec, max_tokens: int, what: str, emit) -> bool:
    """Run the confirm-or-correct pass off the turn. False (inline) when nothing was said yet — the pass IS the
    answer — or when a typed turn lent its collector (`proactive._TURN_SPEAKER`): no later line exists there."""
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
    """SKIP (or a repeat of what was said) is silence; anything else is said as a follow-up. Never raises."""
    from nucleo.flash import second_pass
    from nucleo.llm.fast_client import FastClient
    from voice import proactive, speech
    from voice.tag_protocol import strip_tags
    m, t0, raw = {}, time.monotonic(), ""
    try:
        async for delta in FastClient().stream(_messages(sys2, user_text), spec=spec, max_tokens=max_tokens, metrics=m):
            raw += delta or ""
    except Exception as e:  # noqa: BLE001 — a failed confirmation leaves the first words standing
        logger.warning(f"{what} (detached) failed: {e!r}")
    row = _note(what, t0, m, len(sys2) + len(user_text), True)
    emit("perf", f"⏱ segundo pase «{what}» {row['ms']} ms aparte (no retuvo el turno) · prompt {row['prompt_tokens']} "
                 f"tok · TTFT {row['ttft_ms']} ms", role="system", extra=row)
    text = speech.sanitize(strip_tags(raw, lambda *a, **k: None, True)[0], drop_metadata=False)
    if not text or text.upper().startswith("SKIP") or second_pass.still_held(text, said):
        emit("brain", "🤐 segundo pase: SKIP — lo ya dicho contestaba", role="system", text=f"{what}: {said[:120]}",
             extra={"cat": "flash", "detached": True})
        return ""
    emit("brain", "🩹 segundo pase: corrige lo ya dicho — llega como seguimiento", role="system",
         text=f"{what}: {text[:160]}", extra={"cat": "flash", "detached": True})
    await proactive.notify("zaelar", text, speak=True, kind="notify")
    return text
