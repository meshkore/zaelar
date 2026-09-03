"""The lead-in filler sounds BEFORE the reply, as the reply's own first segment — and only when the reply
is actually slow (V2-529, 2026-08-31).

The two operator reports this closes, both measured live:
  · “the voice does it backwards: it plays the reply first and then the interjection” — the say-path filler was
    authorized by LiveKit's speech scheduler only when the CURRENT speech (the reply) finished playing.
    Session e081f343: the filler's synthesis fired at the exact millisecond the reply's playout ended.
  · “if we are going to answer in one second or less, there is no need to add those interjections” — the timer fired at
    600 ms against a measured TTFT of 1.9-2.8 s, so practically every turn got one.

⚠️ The intermediate design (pre-synthesized frames from a `tts_node` wrapper) was ALSO wrong and only a
live turn showed it: this pipeline calls `tts_node` from `_start_segment()`, which runs when the first
text chunk arrives — a node that only exists once text exists can never measure that the text is late.
`test_the_wiring_uses_llm_node_and_NOT_tts_node` is the guard that keeps that lesson.

These tests drive the wrappers with fake inner nodes (pure asyncio, no LiveKit session): the contract is
about ORDER, CONDITIONS and what reaches the transcript — not about audio."""
from __future__ import annotations

import asyncio

import pytest
from livekit.agents.types import FlushSentinel

from voice.engine.speech import filler_audio as fa


class _Brain:
    _last_filler = ""
    _last_spoken = ""
    _last_spoke_at = 0.0


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    fa._reset_for_tests()
    monkeypatch.setenv("ZAELAR_FILLER_MS", "50")   # fast timer for tests
    yield
    fa._reset_for_tests()


def _inner_llm(*, first_after: float, chunks=("Sí, ", "aquí estoy.")):
    async def impl(agent, chat_ctx, tools, model_settings):
        await asyncio.sleep(first_after)
        for c in chunks:
            yield c
    return impl


async def _collect_llm(impl, agent=None):
    out = []
    async for c in fa.llm_node_with_filler(agent, impl, None, None, None):
        out.append(c)
    return out


def _run(coro):
    return asyncio.run(coro)


def _shape(out):
    return ["FLUSH" if isinstance(c, FlushSentinel) else c for c in out]


def test_an_armed_slow_turn_emits_the_filler_and_a_FLUSH_before_the_reply(monkeypatch):
    """The core. The FlushSentinel is not decoration: it CLOSES the segment, which is the whole reason
    this is not v1 — without it LiveKit's sentence tokenizer retains a short unpunctuated phrase and it
    comes out glued to the reply, which is the 2026-08-14 bug."""
    monkeypatch.setattr(fa, "_pick_phrase", lambda brain, kind="neutral": "A ver…")
    fa.arm(_Brain())
    out = _run(_collect_llm(_inner_llm(first_after=0.3)))
    assert _shape(out) == ["A ver… ", "FLUSH", "Sí, ", "aquí estoy."], \
        f"filler + flush must come FIRST, then the reply untouched — got {_shape(out)}"


def test_a_fast_reply_gets_NO_filler(monkeypatch):
    """“If we are going to answer in one second or less, do not add the interjection.”"""
    monkeypatch.setattr(fa, "_pick_phrase", lambda brain, kind="neutral": "A ver…")
    fa.arm(_Brain())
    out = _run(_collect_llm(_inner_llm(first_after=0.0)))
    assert _shape(out) == ["Sí, ", "aquí estoy."], "a fast reply must pass through byte-identical"


def test_an_UNARMED_generation_never_gets_a_filler(monkeypatch):
    """A generation this turn did not arm (kickoff, or any future caller of llm_node) never sounds one,
    however slow it is."""
    monkeypatch.setattr(fa, "_pick_phrase", lambda brain, kind="neutral": "A ver…")
    out = _run(_collect_llm(_inner_llm(first_after=0.3)))
    assert _shape(out) == ["Sí, ", "aquí estoy."]


def test_the_arm_is_consumed_ONCE_and_expires():
    fa.arm(_Brain())
    assert fa._consume_arm() is not None
    assert fa._consume_arm() is None, "consume-once: a second generation cannot inherit the arm"
    fa.arm(_Brain())
    fa._arm = (fa._arm[0] - (fa._ARM_TTL_S + 1),) + fa._arm[1:]
    assert fa._consume_arm() is None, "a stale arm (dead turn) must not fire a filler minutes later"


def test_the_filler_is_STRIPPED_from_the_transcript_but_the_reply_is_not(monkeypatch):
    """`transcription_node`'s output is what LiveKit forwards to the subtitles AND writes into chat_ctx
    (`forwarded_text`, not the LLM's raw generated_text). The filler is spoken, never written there."""
    monkeypatch.setattr(fa, "_pick_phrase", lambda brain, kind="neutral": "A ver…")
    fa.arm(_Brain())
    _run(_collect_llm(_inner_llm(first_after=0.3)))   # this marks the phrase for stripping

    async def passthrough(agent, text, model_settings):
        async for c in text:
            yield c

    async def go():
        async def source():
            for c in ("A ver… ", "Sí, ", "aquí estoy."):
                yield c
        return [c async for c in fa.transcription_node_without_filler(None, passthrough, source(), None)]

    assert _run(go()) == ["Sí, ", "aquí estoy."], "the filler must not reach subtitles or chat history"


def test_the_strip_is_consumed_once_so_a_real_reply_saying_the_same_survives(monkeypatch):
    """A reply that genuinely opens with the same interjection is only ever dropped for the ONE filler
    that is pending — never for every turn afterwards."""
    fa.mark_for_strip("A ver…")
    assert fa.strip_if_filler("A ver… ") is True
    assert fa.strip_if_filler("A ver… ") is False, "second occurrence is the model's own words"


def test_the_filler_never_talks_over_the_operator(monkeypatch):
    """The 2026-08-15 lesson (session 319252e7) survives the mechanism change."""
    import voice.proactive as proactive
    monkeypatch.setattr(proactive, "user_speaking", lambda: True)
    assert fa._pick_phrase(_Brain()) == "", "user speaking → the filler stays silent"


def test_pick_phrase_updates_the_anti_echo_and_varies(monkeypatch):
    import voice.proactive as proactive
    monkeypatch.setattr(proactive, "user_speaking", lambda: False)
    b = _Brain()
    p1 = fa._pick_phrase(b)
    assert p1, "with a healthy pool a phrase must come out"
    assert b._last_filler == p1 and b._last_spoken == p1 and b._last_spoke_at > 0, \
        "anti-echo: the mic must not re-capture the filler as an operator turn"
    assert fa._pick_phrase(b) != p1, "anti-repetition: never the same phrase twice in a row"


def test_the_announce_emits_the_marked_chat_event_and_the_debug_trail(monkeypatch):
    """V2-122 addenda contract, carried over: the filler IS something the agent said — it goes to the chat
    wall with its own dedicated kind (never inside the reply's bubble), plus the observability trail."""
    events = []
    import voice.observer as observer
    monkeypatch.setattr(observer, "emit",
                        lambda kind, label, text="", role="", extra=None, **kw:
                        events.append({"kind": kind, "text": text, "role": role}))
    fa._announce("A ver…")
    kinds = [e["kind"] for e in events]
    assert "filler" in kinds and "brain" in kinds
    f = next(e for e in events if e["kind"] == "filler")
    assert f["role"] == "assistant" and f["text"] == "A ver…"


def test_a_model_error_PROPAGATES(monkeypatch):
    """The wrapper must never swallow the model's failure — a dead provider has to reach the turn manager
    exactly as before, or an outage looks like a silent agent."""
    async def broken(agent, chat_ctx, tools, model_settings):
        raise RuntimeError("provider down")
        yield  # pragma: no cover

    with pytest.raises(RuntimeError, match="provider down"):
        _run(_collect_llm(broken))


def test_the_default_delay_honors_the_operators_one_second_rule(monkeypatch):
    """ZAELAR_FILLER_MS default moved 600 → 1100: a reply within ~a second never gets a filler. 0 disables."""
    monkeypatch.delenv("ZAELAR_FILLER_MS", raising=False)
    assert fa.delay_ms() >= 1000, "the default must not fire fillers on ~1s replies (operator's rule)"
    monkeypatch.setenv("ZAELAR_FILLER_MS", "0")
    assert not fa.enabled(), "ZAELAR_FILLER_MS=0 stays the kill-switch"


def test_the_wiring_uses_llm_node_and_NOT_tts_node():
    """The lesson of the discarded v2.5, kept as a guard: `tts_node` is only called from `_start_segment()`
    — i.e. once the first text chunk exists — so a filler hung there can never fire on a slow turn. The
    live proof: TTFT 2.5s with the timer at 1.1s produced NO filler at all."""
    from pathlib import Path
    # The overrides moved to their own module (V2-538, the architecture ratchet asked); the guard follows the
    # code, which is exactly what it caught when they moved.
    body = (Path(__file__).resolve().parents[3] / "voice/engine/pipeline/zaelar_agent.py").read_text()
    assert "llm_node_with_filler" in body and "transcription_node_without_filler" in body, \
        "the filler enters through llm_node and is stripped in transcription_node"
    assert "tts_node_with_filler" not in body, \
        "tts_node cannot observe a late reply — it is only created once text exists"
    # …and the entrypoint still MOUNTS it: a class nobody instantiates is a node nobody overrides.
    entry = (Path(__file__).resolve().parents[3] / "voice/engine/pipeline/agent.py").read_text()
    assert "from .zaelar_agent import ZaelarAgent" in entry and "ZaelarAgent(instructions=" in entry


def test_a_turn_that_ARMS_AFTER_the_deadline_still_gets_its_filler(monkeypatch):
    """The race measured live on 2026-08-31, and the reason the deadline is not a single sleep: this node
    is entered before the brain's `_run_inner` reaches its arm call (prompt build + tool selection sit in
    between), and how far before varies per turn. One turn armed 150 ms BEFORE the deadline and fired; the
    very next armed ~400 ms AFTER it and produced NO filler at all, with TTFT 3.26 s — a turn that plainly
    deserved one. Past the deadline we keep polling for the arm, still racing the model's first chunk."""
    monkeypatch.setattr(fa, "_pick_phrase", lambda brain, kind="neutral": "A ver…")

    async def go():
        async def arm_late():
            await asyncio.sleep(0.20)   # deadline is 50 ms in this fixture: the arm loses the race
            fa.arm(_Brain())
        asyncio.get_running_loop().create_task(arm_late())
        return await _collect_llm(_inner_llm(first_after=0.6))

    assert _shape(_run(go())) == ["A ver… ", "FLUSH", "Sí, ", "aquí estoy."], \
        "an arm that arrives after the deadline must still fire — losing that race loses the filler"


def test_but_an_arm_that_NEVER_arrives_stays_silent(monkeypatch):
    """The other half of the race fix: waiting for a late arm must not become "fire whenever". A
    generation that never arms (the kickoff) gets nothing, however slow the model is — the greeting
    nobody is waiting for never gets a “Well…”.

    ⚠️ This does NOT cover `_ARM_GRACE_S` itself, and saying so is the point: disarming that bound leaves
    every test green, because the first-chunk future always resolves (chunk, end, or error) and the loop
    exits there anyway. The bound is a guard against spinning on a model that hangs forever, not a
    behavioural boundary — claiming otherwise would be crediting coverage that does not exist."""
    monkeypatch.setattr(fa, "_pick_phrase", lambda brain, kind="neutral": "A ver…")
    monkeypatch.setattr(fa, "_ARM_GRACE_S", 0.1)
    out = _run(_collect_llm(_inner_llm(first_after=0.5)))
    assert _shape(out) == ["Sí, ", "aquí estoy."], "no arm ever → no filler, however slow the model is"
