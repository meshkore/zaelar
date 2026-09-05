"""voice/engine/llm/providers/acc_notices.py — what the operator HEARS about held and dropped fragments.

Extracted from `providers/nucleo.py` on 2026-09-03 paying the architecture ratchet (V2-567's show-vs-close
guard crossed the provider's ceiling by 8 lines: the table calls for extracting a concern, not raising the
number — same instalment as `workers/resume.py` and `workers/ended.py`). It is a COHESIVE concern: the
accumulator's NOTICES — the pure decision of when to speak (`_acc_notice_plan`, testable without a loop), the
spoken acknowledgment of a dropped chain with its judge rescue (`_speak_acc_drop`, V2-096/V2-102), and the
one reassurance ping of a long hold (`_schedule_acc_nudge`, generation-pinned). None of it touches the
accumulator's buffer — these functions have a mouth, never hands.

`providers/nucleo.py` keeps ALIASES with the historical names: its own call sites and the voice unit tests
(`test_nucleo_accumulator_notice`, `test_nucleo_speak_acc_drop`) import through the provider unchanged.
"""
from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:                  # runtime import would be circular; the annotations are strings
    from voice.engine.llm.providers.nucleo import NucleoLLM

_ACC_NUDGE_S = float(os.getenv("ZAELAR_ACC_NUDGE_S", "8.0"))


def _acc_notice_plan(action: str, dropped: str, n_before: int) -> tuple[bool, bool]:
    """Pure decision extracted from one `Accumulator.offer()` outcome (2026-08-15 fix): (speak_drop_notice,
    start_fresh_chain). Kept separate from the async plumbing (`_speak_acc_drop`/`_schedule_acc_nudge`) so it is
    testable without an event loop or a live voice session.

    `speak_drop_notice` fires whenever this call's `dropped` is non-empty, in EITHER branch — the bug this fixes
    is exactly that it used to only ever surface on "act" (see `Accumulator.offer` docstring). `start_fresh_chain`
    is true when this "hold" begins a chain with no prior context to lean on: either nothing was buffered before
    (`n_before == 0`) or what WAS buffered just got wiped by the drop — in both cases the operator is now waiting
    on a reply to a fragment the system has never seen the rest of, which is the case that needs a nudge if it
    drags on. `action != "hold"` never starts a chain (it just resolved one)."""
    fresh_chain = action == "hold" and (bool(dropped) or n_before == 0)
    return bool(dropped), fresh_chain


async def _speak_acc_drop(dropped: str) -> None:
    """A stale fragment chain just got discarded (`Accumulator`'s gap valve, > MAX_GAP_S). Silence here IS the
    bug: acknowledge it out of band (`voice.proactive.speaker()`, the same lead-in channel V2-093 uses for
    fillers) so the operator learns their earlier words weren't just ignored. Best-effort: no live speaker
    (probe/text channel, no session) → no-op; never talks over the operator mid-sentence
    (`proactive.user_speaking()`).

    V2-102: before settling for the generic "I missed that", give the JUDGE one more look at what got dropped —
    a genuinely complete or clarification-worthy request shouldn't get the same shrug as real gibberish just
    because the operator paused too long. `ASK` speaks the clarifying question right here, same as the live
    path. `COMPLETE` still speaks the generic notice (the operator needs SOME immediate signal) but ALSO pushes
    a `[SISTEMA]` note (`voice/brain_notes.py`) so the content itself surfaces on the NEXT turn instead of
    vanishing — never spoken unprompted, since nothing was just asked. Only a genuine `INCOMPLETE` verdict (the
    judge agrees there's nothing worth resurrecting) keeps today's plain behavior."""
    # PRESERVING COMES FIRST, SPEAKING SECOND — and the order is the fix (2026-08-21, operator's rule: nothing he
    # says may be lost). Everything below used to sit AFTER `if speak is None or user_speaking(): return`, so the
    # judge call and the `[SISTEMA]` note that rescue the content only ran when a live speaker happened to be
    # available and the operator happened to be quiet. In the probe/text channel there is never a speaker, and
    # mid-sentence there never is either: in both cases the discarded text vanished completely — no note, no
    # judge, no trace — which is exactly the loss this function was written to prevent. Rescuing the CONTENT and
    # acknowledging it OUT LOUD are two different jobs; only the second one needs a mouth.
    text = ""
    try:
        from voice.engine.core import langs
        text = langs.current_language().acc_fragment_dropped
    except Exception:
        pass
    try:
        from nucleo.flash import segmenter
        verdict, extra = await segmenter.judge(dropped)
        if verdict == "ask" and extra:
            text = extra
        elif verdict == "complete":
            try:
                from voice import brain_notes
                brain_notes.push(
                    f'[SISTEMA] El operador dijo esto antes de una pausa larga y no llegó a procesarse: '
                    f'"{dropped}". Si sigue vigente, atiéndelo en tu próxima respuesta.')
            except Exception:
                pass
    except Exception:
        pass          # judge unavailable → fall back to the plain generic notice, same as before V2-102
    try:
        from voice import proactive
        speak = proactive.speaker()
        if speak is None or proactive.user_speaking() or not text:
            return        # nothing to say it WITH; the content is already safe above
        r = speak(text)
        if asyncio.iscoroutine(r):
            await r
    except Exception:
        pass


def _schedule_acc_nudge(brain: "NucleoLLM", gen: int) -> None:
    """Give the operator ONE gentle audible sign that a long HOLD is still "listening", not hung (the silence
    reported live: a 64s gap with zero signal either way). A pure reassurance ping, never an action: it never
    touches the accumulator's buffer, so it can't violate V2-096's no-timed-flush invariant — a fragment that
    never continues still gets no reply, only an acknowledgement that the system is waiting on it.

    `gen` pins the nudge to THIS chain (`brain._acc_gen`, bumped by the caller every time a chain resolves or gets
    dropped): if the chain already moved on by the time the delay elapses, the nudge checks the counter and
    no-ops instead of firing after the fact for a conversation that has already continued elsewhere."""
    async def _run() -> None:
        await asyncio.sleep(_ACC_NUDGE_S)
        if getattr(brain, "_acc_gen", None) != gen or not brain._acc.pending():
            return
        try:
            from voice import proactive
            speak = proactive.speaker()
            if speak is None or proactive.user_speaking():
                return
            from voice.engine.core import langs
            r = speak(langs.current_language().acc_still_listening)
            if asyncio.iscoroutine(r):
                await r
            from voice.observer import emit
            emit("brain", "🕒 sigo esperando el resto de la frase", role="system", extra={"cat": "flash"})
        except Exception:
            pass
    from voice.engine.llm.providers.nucleo import _spawn   # lazy: provider owns the task registry
    _spawn(_run(), "acc_nudge")
