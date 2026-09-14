"""hard_turn.py — the DETERMINISTIC half of a hard interrupt, resolved before any model runs (T136, V2-688).

## Why this is its own module

«cierra los widgets», «para», «silencio» are always attended to, they skip the attention gate, and they are
executed deterministically — never left to a model and never buried in a large turn. That last clause is the
receipt: the original bug was a `close` order that fell OUTSIDE the excerpt of a 14 000-char turn and simply
never happened.

Everything the decision needs is here, in one place, because it is four questions that keep being confused
with each other, and each of the four was wrong at some point:

1. **Is a short stop about a WORKER rather than about the voice?** (V2-038 §v3·M) With Brain Workers alive and
   words that refer to WORK, «para eso» means stop the errand. The turn must then CONTINUE, so the model can
   call `stop_worker` — returning here would silence the voice and leave the worker running.
2. **Is it about MUSIC?** (2026-07-16) LiveKit's barge-in cuts ZAELAR's voice, never the music stream, so
   without this the operator had to say it twice.
3. **Is it a canvas close?** Then it is emitted immediately, before anything else is decided.
4. **Was closing the WHOLE request?** (V2-688) This is the one nobody had asked. Measured live on flow
   `T10·c053`: «close all, open agenda, connect to my google calendar» produced the entire event chain
   `✋ interrupción dura atendida · widget close · flow end` — no tool, no model call, no reply. The canvas
   cleared, which looks enough like obedience to hide the two orders thrown away with it.

## The contract

`handle()` answers with the text the turn should CONTINUE with, or `None` when the turn ends here. That
shape is the point: the caller has one branch instead of four, and «continue» versus «stop» stops being a
property of where you are in a nest of conditionals.

The close's guarantee is unchanged and is expressed as an ORDER: the `widget close` event is emitted before
the remainder is even computed, so no later decision — or failure — can lose the one order this whole
mechanism exists never to lose.
"""
from __future__ import annotations

import asyncio


async def handle(text: str, hard: str, emit) -> str | None:
    """Resolve a hard interrupt. Returns the text the turn should go on with, or None to end the turn.

    `emit` is injected rather than imported: the voice provider already holds a fail-safe `emit` (a no-op when
    the observer cannot be imported), and reaching for a second one here would give this module a different
    observability failure mode from the turn it belongs to.
    """
    # 1 · A short STOP with live workers and words about WORK is not silence — it is «stop the errand». The
    #     turn continues so the model can call `stop_worker` (with its deterministic post-stream backstop).
    worker_stop = False
    if hard == "stop":
        try:
            from nucleo import dispatch as _d0
            from nucleo.flash import router as _router0
            worker_stop = _d0.has_active() and _router0.looks_like_stop_work(text)
        except Exception:                      # noqa: BLE001 — an unreadable ledger is «no workers», as before
            worker_stop = False
        # 2 · MUSIC. Deterministic and off-loop: the live `music.playing`/`music.search` rail says whether
        #     something is sounding (µs, in RAM). Stopping a WORKER wins; otherwise stop the music.
        if not worker_stop:
            try:
                from nucleo import rails as _rails0
                if _rails0.get("music.playing") or _rails0.get("music.search"):
                    from connectors import music as _music0
                    await asyncio.to_thread(_music0.control, "stop")
                    _rails0.resolve("music.playing")
                    _rails0.resolve("music.search")
                    emit("music", "🎵 stop (interrupción dura · música viva)", text=text[:80],
                         role="system", extra={"reason": "hard_interrupt"})
            except Exception:                  # noqa: BLE001
                pass
    if worker_stop:
        return text                            # the turn runs, untouched — the model owns this one

    emit("ambient", "✋ interrupción dura atendida", text=text[:160], role="user",
         extra={"cmd": hard, "reason": "hard_interrupt"})

    rest = ""
    if hard == "close":
        emit("widget", "close", extra={"src": "flash"})     # 3 · close EVERY widget, now, before anything else
        # 4 · V2-688 — and only THEN ask whether closing was the whole request. The closing clause is removed
        #     from what the model reads: handed «close all» against an already-empty canvas it re-emits it
        #     (the context-bleed shape V2-635 catalogued), and that second close would land on whatever this
        #     same sentence just asked to open.
        try:
            from voice import attention as _att
            rest = _att.close_all_remainder(text)
        except Exception:                      # noqa: BLE001 — unreadable remainder = the old behaviour
            rest = ""
    if not rest:
        return None                            # 'stop' → the barge-in already cut the TTS; we do not reply

    emit("ambient", "✋ cierre hecho · sigue el resto de la orden", text=rest[:160],
         role="system", extra={"reason": "hard_interrupt_remainder"})
    return rest
