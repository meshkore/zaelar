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
    deliver(text)
    return text


def deliver(text: str) -> None:
    """The follow-up is THIS turn's answer, so it leaves the way the turn's words did, now: on the wall as an agent
    line, into the dialog window, and to the session's speaker, which LiveKit queues right behind the turn's own
    speech. Never through `proactive.notify` (demo sandbox build 86, pass 2, M2: its ticket queue sat behind an
    earlier say that never completed, gave up at 180 s and turned «Over the last month Apple is at 343.83 USD…»
    into a [SISTEMA] note glued onto a turn 25 steps later), and never parked for the next turn."""
    from nucleo.flash import dialog
    from voice import observer, proactive
    observer.emit("brain", "🗣 seguimiento del turno", text=text, role="assistant", extra={"wall": "zaelar"})
    dialog.note_spoken(text)
    say = proactive.speaker()
    if say is not None:
        r = say(text)
        if asyncio.iscoroutine(r):            # held, never awaited: nothing waits on its playout
            task = asyncio.ensure_future(r)
            _LIVE.add(task)
            task.add_done_callback(_LIVE.discard)


# ── the model's words wait while a SURE answer verdict may replace its call (V2-831 T-19 R16) ─────────────────────

def holds(brief) -> str:
    """The card of a SURE `screen_action` whose action ANSWERS (`output.answer`): its words compose from the op's
    data, so what the model says first is speculative and is held until its calls are known. "" = not held."""
    try:
        from nucleo.acts import card
        from nucleo.turn import brief as tb
        from widgets import effects
        target, info = tb.read(brief, tb.TARGET_KEY, "", min_confidence=card.VETO_SURE)
        wid, _, act = str(target or "").partition(":")
        return wid if (info or {}).get("used") and effects.carries(wid, act, effects.OUTPUT_ANSWER) else ""
    except Exception as e:  # noqa: BLE001 — an unreadable verdict holds nothing: today's path
        logger.debug(f"follow_up_pass: hold unreadable: {e!r}")
        return ""


def release(held: list, card: str, model_calls, ran_ops, send, emit) -> None:
    """The stream ended: the held words are spoken — unless the model's call on that card did not run as it made it
    (the verdict replaced it, a guard refused it). Then they narrated an act that never ran and are dropped, and the
    op's own answer is the first words (nothing was said, so `detach` runs that pass inline)."""
    from nucleo.turn import promise_kept
    text, held[:] = "".join(held), []
    if text and promise_kept.unrun_model_card(model_calls, ran_ops) == card:
        emit("brain", "🤐 las palabras narraban una llamada que el veredicto sustituyó — no se dicen", role="system",
             text=text[:160], extra={"cat": "flash", "card": card})
    elif text:
        send(text)
