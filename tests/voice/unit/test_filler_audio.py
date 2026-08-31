"""The lead-in filler sounds BEFORE the reply, inside the reply's own speech — and only when the reply is
actually slow (V2-529, 2026-08-31).

The two operator reports this closes, both measured live:
  · «la voz lo hace al revés: primero reproduce la respuesta y después el nexo» — the say-path filler was
    authorized by LiveKit's speech scheduler only when the CURRENT speech (the reply) finished playing.
    Session e081f343: the filler's synthesis fired at the exact moment the reply's playout ended.
  · «si vamos a contestar en un segundo o menos, no es necesario meter esos nexos» — the timer fired at
    600 ms against a measured TTFT of 1.9-2.8 s, so practically every turn got one.

These tests drive `tts_node_with_filler` with a fake inner tts_node (pure asyncio, no LiveKit): the wrapper's
contract is about ORDER and CONDITIONS, not about audio."""
from __future__ import annotations

import asyncio

import pytest

from voice.engine.speech import filler_audio as fa


class _Brain:
    _last_filler = ""
    _last_spoken = ""
    _last_spoke_at = 0.0


class _Frame:
    def __init__(self, tag: str) -> None:
        self.tag = tag

    def __repr__(self) -> str:  # readable failures
        return f"<F {self.tag}>"


class _Agent:
    """Stands in for the LiveKit Agent: the wrapper only asks it for the activity's tts."""

    def _get_activity_or_raise(self):
        class _A:
            tts = object()
        return _A()


def _default_impl(*, text_delay: float, frames: list[_Frame], frames_delay: float = 0.0):
    """A fake default tts_node: consumes the text stream (which the wrapper spies on) and yields frames.
    `frames_delay` models real TTS synthesis latency — the first FRAME always lags the first TEXT."""
    async def impl(agent, text, model_settings):
        async for _ in text:
            pass
        if frames_delay:
            await asyncio.sleep(frames_delay)
        for fr in frames:
            yield fr
    return impl


def _text_stream(*, first_after: float, chunks=("hola ", "mundo.")):
    async def gen():
        await asyncio.sleep(first_after)
        for c in chunks:
            yield c
    return gen()


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    fa._reset_for_tests()
    monkeypatch.setenv("ZAELAR_FILLER_MS", "50")   # fast timer for tests
    monkeypatch.setattr(fa, "_voice_key", lambda: ("test", "voice", "es"))
    yield
    fa._reset_for_tests()


def _seed_cached_filler(phrase="A ver…"):
    fa._cache[("test", "voice", "es", phrase)] = [_Frame("filler-1"), _Frame("filler-2")]
    return phrase


def _run(coro):
    return asyncio.run(coro)


async def _collect(agent, impl, text):
    out = []
    async for fr in fa.tts_node_with_filler(agent, impl, text, None):
        out.append(fr)
    return out


def test_an_armed_slow_turn_gets_the_filler_frames_FIRST_then_the_reply(monkeypatch):
    """The core: reply text arrives late → the filler's cached frames lead the speech, the reply follows.
    This is the order the operator asked for, guaranteed structurally (same speech, no scheduler race)."""
    phrase = _seed_cached_filler()
    monkeypatch.setattr(fa, "_pick_phrase", lambda brain: phrase)
    fa.arm(_Brain())
    reply = [_Frame("reply-1"), _Frame("reply-2")]
    out = _run(_collect(_Agent(), _default_impl(text_delay=0, frames=reply),
                        _text_stream(first_after=0.3)))
    tags = [f.tag for f in out]
    assert tags == ["filler-1", "filler-2", "reply-1", "reply-2"], \
        f"the filler must SOUND BEFORE the reply, inside the same speech — got {tags}"


def test_a_fast_reply_gets_NO_filler(monkeypatch):
    """«Si vamos a contestar en un segundo o menos, no metas el nexo»: first text before the delay → clean."""
    phrase = _seed_cached_filler()
    monkeypatch.setattr(fa, "_pick_phrase", lambda brain: phrase)
    fa.arm(_Brain())
    reply = [_Frame("reply-1")]
    # text arrives instantly but the first FRAME lags past the timer (synthesis latency): the decision must
    # key on the first TEXT, not the first frame — otherwise every turn would still get a filler.
    out = _run(_collect(_Agent(), _default_impl(text_delay=0, frames=reply, frames_delay=0.15),
                        _text_stream(first_after=0.0)))
    assert [f.tag for f in out] == ["reply-1"], "a fast reply must come out byte-identical, no filler"


def test_an_UNARMED_generation_never_gets_a_filler(monkeypatch):
    """A `say()` speech (greeting, proactive delivery) or any non-brain generation never armed — even if its
    text were slow, no filler may sound: only the turn that armed one can."""
    phrase = _seed_cached_filler()
    monkeypatch.setattr(fa, "_pick_phrase", lambda brain: phrase)
    reply = [_Frame("reply-1")]
    out = _run(_collect(_Agent(), _default_impl(text_delay=0, frames=reply),
                        _text_stream(first_after=0.3)))
    assert [f.tag for f in out] == ["reply-1"]


def test_the_arm_is_consumed_ONCE_and_expires():
    fa.arm(_Brain())
    assert fa._consume_arm() is not None
    assert fa._consume_arm() is None, "consume-once: a second generation cannot inherit the arm"
    fa.arm(_Brain())
    fa._arm = (fa._arm[0] - (fa._ARM_TTL_S + 1), fa._arm[1])
    assert fa._consume_arm() is None, "a stale arm (dead turn) must not fire a filler minutes later"


def test_the_filler_never_talks_over_the_operator(monkeypatch):
    """The 2026-08-15 lesson (session 319252e7) survives the mechanism change: operator speaking → no filler."""
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
    p2 = fa._pick_phrase(b)
    assert p2 != p1, "anti-repetition: never the same phrase twice in a row"


def test_the_announce_emits_the_marked_chat_event_and_the_debug_trail(monkeypatch):
    """V2-122 addenda contract, carried over: the filler IS something the agent said — it goes to the chat
    wall with its own dedicated kind, plus the observability trail."""
    events = []
    import voice.observer as observer
    monkeypatch.setattr(observer, "emit",
                        lambda kind, label, text="", role="", extra=None, **kw:
                        events.append({"kind": kind, "text": text, "role": role}))
    fa._announce("A ver…")
    kinds = [e["kind"] for e in events]
    assert "filler" in kinds, "the marked chat-wall event (kind='filler') must be pushed"
    assert "brain" in kinds, "the observability trail must not disappear"
    f = next(e for e in events if e["kind"] == "filler")
    assert f["role"] == "assistant" and f["text"] == "A ver…"


def test_a_late_first_token_during_synthesis_still_cancels_the_filler(monkeypatch):
    """The re-check after the (possibly slow) synthesis: if the reply began meanwhile, gluing the filler in
    front would only DELAY the reply — skip it."""
    phrase = "A ver…"
    monkeypatch.setattr(fa, "_pick_phrase", lambda brain: phrase)

    text = _text_stream(first_after=0.12)

    async def slow_frames(tts, ph):
        await asyncio.sleep(0.2)   # synthesis slower than the reply's first token
        return [_Frame("filler-1")]
    monkeypatch.setattr(fa, "_frames_for", slow_frames)
    fa.arm(_Brain())
    out = _run(_collect(_Agent(), _default_impl(text_delay=0, frames=[_Frame("reply-1")]), text))
    assert [f.tag for f in out] == ["reply-1"], "reply started during synthesis → no filler"


def test_an_inner_tts_error_PROPAGATES(monkeypatch):
    """The wrapper must never swallow the default impl's failure — a TTS error has to reach the generation
    task exactly as before, or a broken voice looks like a silent one."""
    async def broken(agent, text, model_settings):
        async for _ in text:
            pass
        raise RuntimeError("tts down")
        yield  # pragma: no cover

    with pytest.raises(RuntimeError, match="tts down"):
        _run(_collect(_Agent(), broken, _text_stream(first_after=0.0)))


def test_the_default_delay_honors_the_operators_one_second_rule(monkeypatch):
    """ZAELAR_FILLER_MS default moved 600 → 1100: a reply within ~a second never gets a filler. 0 disables."""
    monkeypatch.delenv("ZAELAR_FILLER_MS", raising=False)
    assert fa.delay_ms() >= 1000, "the default must not fire fillers on ~1s replies (operator's rule)"
    monkeypatch.setenv("ZAELAR_FILLER_MS", "0")
    assert not fa.enabled(), "ZAELAR_FILLER_MS=0 stays the kill-switch"
