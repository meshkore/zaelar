"""Lead-in filler as the reply's FIRST SEGMENT — the only place it can sound before the reply.

History, because this mechanism has died three times and the reasons must survive (V2-529, 2026-08-31;
replaces `voice/engine/llm/providers/lead_in_filler.py`, V2-093/V2-114/V2-122):

  · v1 pushed the filler as a ChatChunk into the reply's text stream and let it ride. LiveKit's sentence
    tokenizer RETAINED it (no sentence-final punctuation, under 20 chars), so it came out GLUED to the
    reply — late.
  · v2 spoke it out of band with `session.say(...)`. That is STRUCTURALLY late: when the filler fires the
    reply is already the scheduler's CURRENT speech, and `AgentActivity._scheduling_task` serializes on
    GENERATION — which for a reply includes waiting for its playout. Measured live (session e081f343):
    the filler's synthesis fired at the exact millisecond the reply's playout ended, and the operator
    heard «Vale, empiezo con la tarea» … «Espera, espera».
  · v2.5 (same day) tried pre-synthesized frames from a `tts_node` wrapper. It cannot work either, and the
    reason is worth keeping: in this livekit-agents the reply is SEGMENTED, and `perform_tts_inference` —
    hence `tts_node` — is only called from `_start_segment()`, which runs when the FIRST TEXT CHUNK
    arrives. A node that only exists once text exists can never measure "the text is late". Verified live:
    a turn with TTFT 2.5s and the timer at 1.1s produced no filler at all.

  · v3 (this module) uses the pipeline's OWN segmentation. The filler is emitted from `llm_node` as text
    followed by a `FlushSentinel`, so it becomes the reply's FIRST SEGMENT: synthesized and played
    immediately, while the model is still thinking, and the reply follows as segment two — in order, in
    the same speech, with no scheduler to fight. A barge-in cancels the whole speech, filler included.

    v1's failure does not come back because v1 had no flush: the sentence tokenizer retained the phrase
    precisely because nothing closed the segment. Here the `FlushSentinel` closes it.

    The filler must not pollute the transcript or the conversation history, so it is stripped in
    `transcription_node` — the seam whose output IS what LiveKit forwards to the frontend and writes into
    `chat_ctx` (`forwarded_text`, not the LLM's raw `generated_text`). Its chat-wall visibility is pushed
    by us explicitly, marked (`kind="filler"`), exactly as V2-122's addenda decided.

The other half of the operator's request — «si vamos a contestar en un segundo o menos, no metas nexo» —
falls out of the same seam: the wrapper races the model's first chunk against the delay (default 1100 ms,
`ZAELAR_FILLER_MS`; 0 disables). A fast reply never gets one.

ARM/CONSUME: only a turn that ARMED the filler can sound one. The voice provider arms per eligible brain
turn (never the kickoff); `say()` speeches (greeting, proactive deliveries) don't go through `llm_node` at
all. The arm is consumed AT FIRE TIME, not at generation start, because the node can begin a hair before
the brain's `_run_inner` gets to arm.
"""
from __future__ import annotations

import asyncio
import os
import time

_ARM_TTL_S = 20.0
_ARM_GRACE_S = 0.8       # past the deadline, how long we keep polling for this turn to ARM (see the race
                         # below). A spin guard, not a behavioural bound: the first-chunk future always
                         # resolves, so in practice the loop exits there — this only saves a model that hangs.
_ARM_POLL_S = 0.05
_arm: tuple[float, object] | None = None   # (monotonic ts, brain)
_last_phrase = ""
_pending_strip: list[str] = []             # phrases emitted as fillers, awaiting removal from the transcript


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
             extra={"cat": "flash", "after_ms": delay_ms(), "path": "segment"})
        emit("filler", "relleno", text=phrase, role="assistant", extra={"cat": "flash"})
    except Exception:
        pass


def mark_for_strip(phrase: str) -> None:
    _pending_strip.append(phrase)


def strip_if_filler(chunk) -> bool:
    """True when this transcript chunk IS a filler we just emitted — consumed once, so a reply that
    genuinely opens with the same interjection is only ever dropped for the filler that is pending."""
    try:
        text = str(chunk).strip()
    except Exception:
        return False
    if not text:
        return False
    for i, ph in enumerate(_pending_strip):
        if text == ph.strip():
            _pending_strip.pop(i)
            return True
    return False


async def llm_node_with_filler(agent, default_impl, chat_ctx, tools, model_settings):
    """Wrap the default llm_node: pass every chunk through unchanged, and — only when this turn ARMED a
    filler and the model's first chunk is later than `delay_ms` — emit the filler text plus a
    `FlushSentinel` first, so it becomes the reply's own first SEGMENT (see module docstring)."""
    from livekit.agents.types import FlushSentinel

    inner = default_impl(agent, chat_ctx, tools, model_settings)
    if asyncio.iscoroutine(inner):
        inner = await inner
    wait_ms = delay_ms()

    q: asyncio.Queue = asyncio.Queue()
    _END = object()

    async def _pump():
        try:
            async for chunk in inner:
                await q.put(("c", chunk))
        except asyncio.CancelledError:
            raise
        except BaseException as e:  # noqa: BLE001 — the model's errors must PROPAGATE, not vanish
            await q.put(("err", e))
            return
        await q.put(("end", _END))

    pump = asyncio.create_task(_pump(), name="filler-llm-pump")
    get_t = asyncio.ensure_future(q.get())
    try:
        if wait_ms > 0:
            # The ARM and the deadline RACE, and the arm can lose: this node is entered before the brain's
            # `_run_inner` reaches its arm call (prompt build + tool selection sit in between), and how far
            # before varies per turn. Measured live 2026-08-31: one turn armed 150 ms BEFORE the deadline
            # (filler fired) and the next armed ~400 ms AFTER it (no filler, with TTFT 3.26 s — a turn that
            # plainly deserved one). So the deadline is not a single sleep: past it we keep polling for the
            # arm, still racing the model's first chunk, for a bounded grace. A generation that never arms
            # (the kickoff) just waits out the grace producing nothing — it is not yielding meanwhile either.
            deadline = time.monotonic() + wait_ms / 1000.0
            give_up = deadline + _ARM_GRACE_S
            while not get_t.done():
                left = min(give_up, max(deadline, time.monotonic()) + _ARM_POLL_S) - time.monotonic()
                await asyncio.wait({get_t}, timeout=max(left, 0.01))
                if get_t.done():
                    break
                now = time.monotonic()
                if now >= deadline:
                    brain = _consume_arm()
                    if brain is not None:
                        phrase = _pick_phrase(brain)
                        if phrase:
                            _announce(phrase)
                            mark_for_strip(phrase)
                            yield phrase + " "
                            yield FlushSentinel()   # closes the segment → played on its own, right now
                        break
                    if now >= give_up:
                        break
        kind, val = await get_t
        while True:
            if kind == "err":
                raise val
            if kind == "end":
                break
            yield val
            kind, val = await q.get()
    finally:
        if not pump.done():
            pump.cancel()


async def transcription_node_without_filler(agent, default_impl, text, model_settings):
    """Drop the filler from what LiveKit FORWARDS: this node's output is the subtitle stream and the text
    that becomes the assistant's `chat_ctx` message. The filler is real speech and IS shown in the chat
    wall — but by our own marked event, never inside the reply's own bubble or the model's history."""
    async def _filtered():
        async for chunk in text:
            if strip_if_filler(chunk):
                continue
            yield chunk

    out = default_impl(agent, _filtered(), model_settings)
    if asyncio.iscoroutine(out):
        out = await out
    if out is None:
        return
    async for chunk in out:
        yield chunk


def _reset_for_tests() -> None:
    global _arm, _last_phrase
    _arm = None
    _last_phrase = ""
    _pending_strip.clear()
