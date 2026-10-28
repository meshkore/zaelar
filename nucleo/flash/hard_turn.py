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


def is_worker_stop(text: str, hard: str) -> bool:
    """Question 1 alone, without effects: is a short stop aimed at a live WORKER? The text probe asks this too
    (V2-778 F2-22), so the bank of brain cases sees «para eso» reach `stop_worker` the way the voice turn does."""
    if hard != "stop":
        return False
    try:
        from nucleo import dispatch as _d0
        from nucleo.flash import router as _router0
        return bool(_d0.has_active() and _router0.looks_like_stop_work(text))
    except Exception:                          # noqa: BLE001 — an unreadable ledger is «no workers», as before
        return False


def remainder(text: str, hard: str) -> str:
    """Question 4 alone: what the sentence ordered besides the close or the stop ("" when that was all)."""
    try:
        from voice import attention as _att
        return (_att.close_all_remainder(text) if hard == "close"
                else _att.stop_remainder(text) if hard == "stop" else "")
    except Exception:                          # noqa: BLE001 — unreadable remainder = the old behaviour
        return ""


async def say_receipt(emit, brain=None) -> str:
    """V2-812 T-04 — a close turn SAYS what it closed and what it kept, in one short line in his language.

    The hard close has no model reply to ride: before this it ended the turn in silence, and in the car session an
    order to close everything that had closed nothing (`bulk_close`, the spare) was indistinguishable from one that
    had worked. Spoken out of band, with the fast lane's manners (never over his voice, anti-echo updated). Returns
    the line ("" when there was nothing to say or no mouth to say it with)."""
    import time as _time

    from nucleo.flash import bulk_close as _bulk
    line = _bulk.take_receipt()
    if not line:
        return ""
    emit("brain", "🧾 close receipt", text=line, role="system", extra={"cat": "flash", "reason": "close_receipt"})
    try:
        from voice import proactive
        speak = proactive.speaker()
        if speak is None or proactive.user_speaking():
            return ""
        if brain is not None:
            brain._last_spoken = line            # anti-echo: the mic must not re-capture it as his turn
            brain._last_spoke_at = _time.time()
        r = speak(line)
        if asyncio.iscoroutine(r):
            await r
        return line
    except Exception as e:                     # noqa: BLE001 — a receipt never breaks the close it describes
        emit("brain", "⚠️ close receipt not spoken", text=f"{type(e).__name__}: {e}"[:160], role="system",
             extra={"cat": "flash", "reason": "close_receipt_failed"})
        return ""


async def names_an_act_on_screen(text: str, emit) -> bool:
    """A stop that NAMES an activity on a card («Stop showing me the Social tab in my mail») is an order about that
    card, not a silence order: decided by the brief's `screen_action` verdict at its licence (refactor2710-07), never by
    the sentence's shape (CRIT-W10). The barge-in already silenced the voice, so the wait costs nothing heard."""
    try:
        from nucleo.turn import brief
        choice, info = await brief.verdict_before_the_turn(text, brief.TARGET_KEY)
        if not (info and info.get("used") and choice and choice != "none"):
            return False
        emit("brain", "✋ el stop nombra una acción de una tarjeta — sigue el turno", text=f"{choice} ← {text[:120]}",
             role="system", extra={"cat": "flash", "reason": "stop_names_an_act", "verdict": choice})
        return True
    except Exception as e:  # noqa: BLE001 — an unreadable verdict keeps the stop as a stop
        emit("brain", "⚠️ stop: the early verdict was not read", text=f"{type(e).__name__}: {e}"[:160], role="system",
             extra={"cat": "flash", "reason": "stop_verdict_failed"})
        return False


async def handle(text: str, hard: str, emit, brain=None) -> str | None:
    """Resolve a hard interrupt. Returns the text the turn should go on with, or None to end the turn.

    `emit` is injected rather than imported: the voice provider already holds a fail-safe `emit` (a no-op when
    the observer cannot be imported), and reaching for a second one here would give this module a different
    observability failure mode from the turn it belongs to.
    """
    # 0 · A STOP HUSHES THE OUT-OF-BAND CHANNEL. Measured in session fce3eff3: four seconds after «y ahora
    #     vas a parar aquí y no vas a hacer nada más», the accumulator's drop notice spoke on its own —
    #     «Perdona, no cogí bien lo que dijiste antes de la pausa» — because the only thing that channel
    #     checks before speaking is whether he is mid-word. A stop is not «quiet for this turn».
    try:
        from voice import proactive as _pro_hush
        _pro_hush.note_hush()
    except Exception:  # noqa: BLE001
        pass

    # 1 · A short STOP with live workers and words about WORK is not silence — it is «stop the errand». The
    #     turn continues so the model can call `stop_worker` (with its deterministic post-stream backstop).
    worker_stop = is_worker_stop(text, hard)
    if hard == "stop":
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

    if hard == "close":
        # 3 · close every card he is not using, now, before anything else (V2-807 T-08: the card in use stays
        #     unless his words name it — `bulk_close`).
        from nucleo.flash import bulk_close as _bulk
        _bulk.close_all(emit, src="flash", text=text)
        await say_receipt(emit, brain)         # V2-812 T-04: never a close in silence
    # 4 · V2-688 — and only THEN ask whether closing was the whole request. The closing clause is removed from what
    #     the model reads: handed «close all» against an already-empty canvas it re-emits it (the context-bleed shape
    #     V2-635 catalogued), and that second close would land on whatever this same sentence just asked to open.
    #     Session 6d19df41 is the stop twin: «No. So no. Stop it. Okay. Show me the WhatsApp messages.» ended here and
    #     the WhatsApp order died in silence. A bare stop still ends the turn; anything else ordered keeps it.
    rest = remainder(text, hard)
    if not rest and hard == "stop" and await names_an_act_on_screen(text, emit):
        return text                            # «Stop showing me the Social tab»: an order about a card, by verdict
    if not rest:
        return None                            # 'stop' → the barge-in already cut the TTS; we do not reply

    emit("ambient", ("✋ cierre hecho · sigue el resto de la orden"
                     if hard == "close" else "✋ stop hecho · sigue el resto de la orden"),
         text=rest[:160], role="system", extra={"reason": "hard_interrupt_remainder"})
    return rest
