"""Lead-in filler as AUDIO INSIDE the reply's own speech — the only place it can sound BEFORE the reply.

History, because this mechanism has died twice and the reasons must survive (V2-529, 2026-08-31; replaces
`voice/engine/llm/providers/lead_in_filler.py`, V-093/V2-114/V2-122):

  · v1 pushed the filler as a ChatChunk into the reply's text stream. The sentence tokenizer retained it
    (no sentence-final punctuation, under 20 chars), so it came out GLUED to the reply — late.
  · v2 spoke it out of band with `session.say(...)`. That is STRUCTURALLY late: when the filler fires the
    reply is already the scheduler's CURRENT speech (scheduled at end-of-turn, generation authorized
    immediately), and `AgentActivity._scheduling_task` strictly serializes — a `say` queued during
    `thinking` is only authorized when the reply FINISHES PLAYING. Measured live (session e081f343,
    2026-08-31): the filler's TTS synthesis fired at the exact millisecond the reply's playout ended, and
    the operator heard «Vale, empiezo con la tarea» … «Espera, espera». The operator's report, verbatim:
    «la voz lo hace al revés. Primero reproduce la respuesta y después el nexo. No tiene ningún sentido.»

  · v3 (this module): the filler is PRE-SYNTHESIZED AUDIO FRAMES yielded as the FIRST audio of the reply
    speech itself, from a `tts_node` wrapper. Inside the current speech there is no scheduler to fight:
    it plays during the model's silence, always before the reply's own audio, and a barge-in kills it
    together with the turn (it IS the turn). No `say`, no second speech, no ordering race.

The other half of the operator's request — «si vamos a contestar en un segundo o menos, no metas nexo» —
falls out of the same seam: the wrapper watches the reply's text stream, and only fires when NO text has
arrived within the delay (default 1100 ms, `ZAELAR_FILLER_MS`; 0 disables). A fast reply never gets one.

ARM/CONSUME: only a turn that ARMED the filler can sound one. The voice provider arms per eligible brain
turn (never the kickoff); `say()` speeches (greeting, proactive deliveries) never arm, and their text
arrives instantly anyway so the timer path is dead for them. The arm is consumed AT FIRE TIME, not at
generation start, because the tts_node can begin a hair before the brain's `_run_inner` gets to arm.
"""
from __future__ import annotations

import asyncio
import os
import time

from loguru import logger

_ARM_TTL_S = 20.0
_SYNTH_WAIT_S = 2.5       # how long a firing turn waits for a cold synthesis before skipping (cache fills anyway)
_arm: tuple[float, object] | None = None   # (monotonic ts, brain)
_last_phrase = ""
_cache: dict[tuple, list] = {}             # (provider, voice, lang, phrase) -> list[rtc.AudioFrame]
_synth_tasks: dict[tuple, asyncio.Task] = {}


def delay_ms() -> int:
    try:
        return int(os.getenv("ZAELAR_FILLER_MS", "1100"))
    except Exception:
        return 1100


def enabled() -> bool:
    return delay_ms() > 0


def arm(brain) -> None:
    """Called by the voice provider once per eligible turn, right where the model is about to be paid."""
    global _arm
    _arm = (time.monotonic(), brain)


def _consume_arm():
    global _arm
    if _arm is None:
        return None
    ts, brain = _arm
    _arm = None
    if time.monotonic() - ts > _ARM_TTL_S:
        return None
    return brain


def _voice_key() -> tuple:
    try:
        from voice.engine.core import langs
        from voice.engine.speech.voices import selected_voice, tts_provider
        return (tts_provider(), selected_voice() or "", langs.current_code())
    except Exception:
        return ("", "", "")


async def _synthesize(tts, key: tuple, phrase: str) -> list | None:
    """One HTTP synthesis via the SAME tts instance the session speaks with (same voice, same sample rate)."""
    try:
        frames = []
        async for ev in tts.synthesize(phrase):
            fr = getattr(ev, "frame", None)
            if fr is not None:
                frames.append(fr)
        if frames:
            _cache[key] = frames
        return frames or None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"filler_audio: synthesis failed for {phrase!r}: {e}")
        return None
    finally:
        _synth_tasks.pop(key, None)


async def _frames_for(tts, phrase: str) -> list | None:
    key = (*_voice_key(), phrase)
    cached = _cache.get(key)
    if cached:
        return cached
    task = _synth_tasks.get(key)
    if task is None:
        task = asyncio.create_task(_synthesize(tts, key, phrase), name=f"filler-synth:{phrase[:12]}")
        _synth_tasks[key] = task
    try:
        # shield: on timeout the synthesis keeps running and fills the cache for the NEXT turn.
        return await asyncio.wait_for(asyncio.shield(task), _SYNTH_WAIT_S)
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
        return None


def prime_soon(tts) -> None:
    """Background pre-synthesis of the current language's pool, prewarm-style: fire-and-forget at session
    start so the FIRST filler of a session doesn't pay the cold-synthesis wait."""
    async def _prime():
        try:
            from voice.engine.core import langs
            pool = []
            code = langs.current_code()
            try:
                pool = list(getattr(langs.spec(code), "fillers", ()) or ())
            except Exception:
                pool = []
            for phrase in pool[:6]:
                key = (*_voice_key(), phrase)
                if key not in _cache and key not in _synth_tasks:
                    await _synthesize(tts, key, phrase)
        except Exception:
            pass
    try:
        asyncio.get_running_loop().create_task(_prime(), name="filler-prime")
    except RuntimeError:
        pass


def _pick_phrase(brain) -> str:
    """Same guards the say-path filler had: never over the operator's voice, varied, anti-echo updated."""
    global _last_phrase
    try:
        from voice import proactive as _pro
        if _pro.user_speaking():
            return ""
    except Exception:
        pass
    try:
        from voice.engine.core import langs
        last = getattr(brain, "_last_filler", "") or _last_phrase
        phrase = langs.pick_filler(last)
    except Exception:
        return ""
    if not phrase:
        return ""
    _last_phrase = phrase
    try:
        brain._last_filler = phrase
        # anti-echo (the mic must not re-capture it) — never the reply-context field the directed-content
        # judge reads (V2-105/V2-109): a filler carries no topic and would misclassify the operator's next
        # turn. A source guard in test_nucleo_directed_context.py bans that field's name from this file.
        brain._last_spoken = phrase
        brain._last_spoke_at = time.time()
    except Exception:
        pass
    return phrase


def _announce(phrase: str) -> None:
    """The filler's visibility contract (V2-122 addenda): observability + an EXPLICIT chat-wall event with
    its own kind, pushed synchronously at the decision — always before any real reply text exists."""
    try:
        from voice.observer import emit
        emit("brain", "💬 relleno de espera (lead-in)", text=phrase, role="system",
             extra={"cat": "flash", "after_ms": delay_ms(), "path": "audio"})
        emit("filler", "relleno", text=phrase, role="assistant", extra={"cat": "flash"})
    except Exception:
        pass


_END = object()


async def tts_node_with_filler(agent, default_impl, text, model_settings):
    """Wrap the default tts_node: pass everything through unchanged, and — only when this turn ARMED a
    filler and the reply's first text hasn't arrived within `delay_ms` — yield the filler's cached audio
    frames FIRST. Inside the reply speech there is no scheduler to fight (see module docstring)."""
    wait_ms = delay_ms()
    first_text = asyncio.Event()

    async def _spy():
        async for chunk in text:
            if chunk and not first_text.is_set():
                first_text.set()
            yield chunk

    inner = default_impl(agent, _spy(), model_settings)
    q: asyncio.Queue = asyncio.Queue()

    async def _pump():
        try:
            async for fr in inner:
                await q.put(("f", fr))
        except asyncio.CancelledError:
            raise
        except BaseException as e:  # noqa: BLE001 — the default impl's errors must PROPAGATE, not vanish
            await q.put(("err", e))
            return
        await q.put(("end", _END))

    pump = asyncio.create_task(_pump(), name="filler-tts-pump")
    get_t = asyncio.ensure_future(q.get())
    timer = asyncio.ensure_future(asyncio.sleep(max(wait_ms, 1) / 1000.0))
    try:
        done, _ = await asyncio.wait({get_t, timer}, return_when=asyncio.FIRST_COMPLETED)
        if wait_ms > 0 and timer in done and not get_t.done() and not first_text.is_set():
            brain = _consume_arm()
            if brain is not None:
                phrase = _pick_phrase(brain)
                if phrase:
                    tts = None
                    try:
                        tts = agent._get_activity_or_raise().tts
                    except Exception:
                        tts = None
                    frames = (await _frames_for(tts, phrase)) if tts is not None else None
                    # re-check: the reply may have started while we synthesized — then the filler is
                    # unnecessary (a fast-enough reply) and gluing it in front would only delay it.
                    if frames and not first_text.is_set():
                        _announce(phrase)
                        for fr in frames:
                            yield fr
        kind, val = await get_t
        while True:
            if kind == "err":
                raise val
            if kind == "end":
                break
            yield val
            kind, val = await q.get()
    finally:
        timer.cancel()
        if not pump.done():
            pump.cancel()


def _reset_for_tests() -> None:
    global _arm, _last_phrase
    _arm = None
    _last_phrase = ""
    _cache.clear()
    _synth_tasks.clear()
