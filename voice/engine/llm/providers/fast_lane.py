"""The deterministic fast lane of the VOICE channel (V2-539), extracted from the provider paying the
architecture ratchet (V2-572 crossed its ceiling; the table calls for extracting a cohesive concern, and this
block always was one: everything a turn does when the action map resolves it without a model).

One behavioural change rides the move, and it is the operator's own words (2026-09-03): the lane used to
execute «IN SILENCE», and he asked for the opposite — *«when you tell him to close something or open
something, he has to say 'ok, done'»*. So after the mutation lands, the lane now speaks a short varied ack
(`langs.pick_ack`: «Hecho.» / «Vale, hecho.» / …) out of band through `voice.proactive.speaker()` — the same
mouth the accumulator notices use, because a fast-lane turn never opens an LLM stream to ride. The ack is
spoken AFTER the execute, so it can never promise what did not happen; if the executor declines (live work
behind the widget, V2-567), the turn falls through whole to the model and no ack sounds. Mirror in
`probe.py::run_turn` (parallel impl — its reply carries the same ack for parity).
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger


async def _speak_ack(brain) -> None:
    """Best-effort, never over the operator's voice, varied, anti-echo updated — the filler's own manners."""
    try:
        from voice import proactive
        from voice.engine.core import langs
        speak = proactive.speaker()
        if speak is None or proactive.user_speaking():
            return
        phrase = langs.pick_ack(getattr(brain, "_last_ack", ""))
        if not phrase:
            return
        brain._last_ack = phrase
        try:
            brain._last_spoken = phrase          # anti-echo: the mic must not re-capture it
            brain._last_spoke_at = time.time()
        except Exception:
            pass
        r = speak(phrase)
        if asyncio.iscoroutine(r):
            await r
    except Exception:
        pass


async def handled(brain, text: str, emit, *, first_turn: bool, t_entry: float, window_max: int) -> bool:
    """A KNOWN short command — one utterance bounded by silence — skips the model entirely: exact
    whole-utterance lookup, allowlisted direct action, executed through the same emit funnel the model's own
    output uses, then confirmed out loud. Anything not verbatim-known (a compound sentence, a negation,
    novelty) falls through untouched — when in doubt, the LLM. It runs AFTER the hard interrupt / echo /
    attention gate (safety and directedness first) and BEFORE the accumulator, but only when NO fragment chain
    is pending: a command spoken mid-chain belongs to the chain's merged phrase, and hijacking it out would
    act on half a sentence. Fail-open by construction (the caller catches): any exception and the turn
    proceeds as if the module did not exist."""
    if first_turn:
        return False
    from nucleo import actionmap as _amap
    if not _amap.enabled() or (getattr(brain, "_acc", None) and brain._acc.fragments):
        return False
    _tm = time.time()
    _amap_hit = _amap.match(text)
    _amap_ms = round((time.time() - _tm) * 1000, 2)
    if _amap_hit is None or not _amap.execute(_amap_hit, emit, phrase=text):
        return False
    _desc = _amap.describe(_amap_hit)
    # `engine: "actionmap"` is not decoration: the viewer's LAYER column reads exactly this field
    # (`DebugPanel.brainName`) and the Master reads it too. Without it a map turn was painted «FlashBrain» /
    # tagged «LLM» — the timeline claimed the model resolved a turn it never saw, which is the one thing this
    # whole mechanism must not make harder to audit. `origin` is the normalized field both surfaces group and
    # count by.
    emit("actionmap", "⚡ action map: direct action (no model)", text=text[:160], role="user",
         extra={"cat": "flash", "action": _desc, "entry": _amap_hit.get("id"),
                "source": _amap_hit.get("source"), "match_ms": _amap_ms,
                "engine": "actionmap", "origin": "actionmap",
                "pre_ms": round((time.time() - t_entry) * 1000, 1), "src": "actionmap"})
    from nucleo.flash import dialog as _dialog0
    _dialog0.push_user(brain._window, text)
    del brain._window[:-window_max]
    try:
        # Conv buffer (mirror of the provider's post-reply write): the NEXT turn — and a worker's
        # recent-conversation block — must see that this phrase was acted on.
        from memory import api as _memory0
        _memory0.write(f"Operador: {text[:200]} · zaelar: [{_desc}]",
                       kind="conv", level="short", importance=0.2, ttl_days=2.0,
                       meta={"source": "conv", "u": text[:400], "a": f"[{_desc}]"})
    except Exception:
        pass
    try:
        # turn.completed for Susurro (V2-539 §3.5): a fast-path turn stays auditable — without this, the
        # auditor goes blind on exactly the turns most likely to need a correction.
        from voice import observer as _obs0
        _obs0.turn_detail(system="", window=list(brain._window)[-6:], tools=[],
                          user=text,
                          decision={"action": _desc, "actionmap": _amap_hit.get("id")})
    except Exception:
        pass
    await _speak_ack(brain)
    return True
