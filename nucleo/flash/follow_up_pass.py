"""First words vs the second pass (V2-831 T-19 R5b, R16).

A pass that can only CONFIRM or CORRECT words already said runs DETACHED (demo build 86, C2: it held the turn ~11 s to
say SKIP): SKIP is silence, a correction a follow-up; the typed channel answers one reply, so there it stays inline.
And under a sure ANSWER verdict the first words wait for the model's call (`Hold`): words that narrated a call the verdict
replaced are never said, and the op's answer is the first words. Every pass is measured apart (`turn_perf.note_pass`).
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
    """The follow-up is THIS turn's answer, so it leaves the way the turn's words did, now: on the wall, into the dialog
    window, and to the session's speaker (queued right behind the turn's speech). Never through `proactive.notify`,
    whose ticket queue once turned an answer into a note glued onto a turn 25 steps later; never parked."""
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


class Hold:
    """The streamed words, held under a SURE `screen_action` that ANSWERS (`output.answer`) — the model's first words are
    speculative there. Decided at the FIRST word: the brief often lands after the stream opens (pass 5, C2)."""

    def __init__(self, brief, send):
        self.brief, self.card, self.send, self.held = brief, None, send, []

    def say(self, piece: str) -> None:
        self.card = holds(self.brief) if piece and self.card is None else self.card
        (self.held.append if piece and self.card else self.send)(piece)

    def release(self, model_calls, ran_ops, emit) -> None:
        """The stream ended: the held words are said, unless the model's call on that card did not run as it made it
        (replaced, refused) — they narrated an act that never ran; dropped, the op's answer pass is the first words."""
        from nucleo.turn import promise_kept
        text, self.held[:] = "".join(self.held), []
        if text and promise_kept.unrun_model_card(model_calls, ran_ops) == self.card:
            emit("brain", "🤐 las palabras narraban una llamada que el veredicto sustituyó — no se dicen", role="system",
                 text=text[:160], extra={"cat": "flash", "card": self.card})
        elif text:
            self.send(text)


def holds(brief) -> str:
    """The card a sure ANSWER verdict names, or "" (nothing held: today's path)."""
    try:
        from nucleo.acts import card
        from nucleo.turn import brief as tb
        from widgets import effects
        target, info = tb.read(brief, tb.TARGET_KEY, "", min_confidence=card.VETO_SURE)
        wid, _, act = str(target or "").partition(":")
        return wid if (info or {}).get("used") and effects.carries(wid, act, effects.OUTPUT_ANSWER) else ""
    except Exception as e:  # noqa: BLE001 — an unreadable verdict holds nothing
        logger.debug(f"follow_up_pass: hold unreadable: {e!r}")
        return ""
