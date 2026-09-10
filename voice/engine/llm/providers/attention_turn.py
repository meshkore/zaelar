"""attention_turn.py — the ATTENTION GATE as the turn sees it: is this one for us, and what does it say?

Extracted from the voice provider (2026-09-10, V2-655: the architecture ratchet went red at 3049 over a
3043 ceiling, and the ratchet's standing instruction is to EXTRACT, never to raise the number). This block
is a clean cut because it needs exactly three things from the provider — the emit seam, the brain's last
reply as judging context, and the turn's text — and hands back exactly two: whether the turn survives, and
the text it survives with. Nothing else of `_run_inner` is touched.

WHAT IT DECIDES. T134: a turn that is not DIRECTED at zaelar produces no action and no reply. In `always`
mode `evaluate_content` asks the fast model about the NATURE of the phrase (the only signal left when there
is no wake word); in `smart` it is the pure heuristic — wake word, or an open conversation window.

WHY THE DISCARDED VERDICT CARRIES THE WINDOW (V2-655). «El sonido ambiente no interrumpe para nada los
contadores» (operator, 2026-09-10). The client paints his «te escucho» ring from these verdicts, and it
used to darken the ring on every ambient one — so a stray word from the room turned the ring off while the
engine's window was still wide open, the client contradicting the engine about the one thing the ring
exists to report. Both verdicts now carry `window_s` and `window_open`, so the ring can expire with the
WINDOW and never with somebody else's noise.
"""
from __future__ import annotations

import time


async def judge(text: str, *, context: str, emit) -> tuple[bool, str, float]:
    """`(directed, text, gate_ms)`. On a directed turn the window is refreshed and the text may GROW — a
    wake word reclaims the fragments discarded as ambient just before it («Ostras, para la música, Johnny»:
    the order arrived before the name). On an ambient one the caller drops the turn; `note_ambient` has
    already kept the tail so a wake word within 10 s can still reclaim it.

    `context` is deliberately cheap — one sentence, not the whole window: the judge needs to know what we
    were doing, not to reconstruct the dialogue. It must be the brain's `_last_reply` and NEVER
    `_last_spoken`, which includes topic-less fillers («Pues…», «Mmm…») — passing those left the judge
    without context right after every filler, and a real follow-up question read as room noise.
    """
    from voice import attention

    t0 = time.time()
    verdict = await attention.evaluate_content(text, context=context)
    gate_ms = round((time.time() - t0) * 1000, 1)
    window = {"window_s": attention.window_s(), "window_open": attention.window_open()}

    if not verdict.directed:
        emit("ambient", "🙉 ambiente — no dirigido a zaelar", text=text[:200], role="user",
             extra={"mode": attention.mode(), "reason": verdict.reason, **window})
        attention.note_ambient(text)
        return False, text, gate_ms

    attention.note_directed()
    if verdict.reason == "wakeword":
        text = attention.reclaim_ambient_tail(text)
    emit("ambient", "👂 dirigido a zaelar",
         extra={"directed": True, "reason": verdict.reason, **window})
    return True, text, gate_ms
