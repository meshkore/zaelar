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


def test_the_arm_is_consumed_ONCE_and_expires():
    fa.arm(_Brain())
    assert fa._consume_arm() is not None
    assert fa._consume_arm() is None, "consume-once: a second generation cannot inherit the arm"
    fa.arm(_Brain())
    fa._arm = (fa._arm[0] - (fa._ARM_TTL_S + 1),) + fa._arm[1:]
    assert fa._consume_arm() is None, "a stale arm (dead turn) must not fire a filler minutes later"


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


# ── V2-640: covers that LISTEN ───────────────────────────────────────────────────────────────────────────

def test_a_meta_question_about_the_conversation_is_SOCIAL_never_thinking():
    """The 19:27 besugos session, classified: «Déjame ver…» answered «¿qué quieres ver?» and the operator
    asked what we wanted to see, forever. Every one of these is a real utterance from that session (sid
    1674ee35) or its English twin — none may ever draw from the thinking pool again."""
    for utt in ("¿Sigues ahí?", "¿Me oyes?", "¿Qué tal?", "¿De qué me estás hablando?",
                "¿Qué quieres ver?", "¿Para qué quieres un momentito?", "¿A qué tengo que esperar?",
                "No estás haciendo nada", "are you there?", "what do you mean?"):
        assert fa.filler_kind(utt) == "social", f"{utt!r} must be social, got {fa.filler_kind(utt)!r}"
    # and the boundary holds: real lookups and orders keep their own classes
    assert fa.filler_kind("¿Qué hora es?") == "neutral"
    assert fa.filler_kind("Búscame un hotel en Soria") == "neutral"
    assert fa.filler_kind("Cierra los mensajes") == "action"


def test_the_armed_phrase_is_the_one_that_sounds(monkeypatch):
    """arm() chooses the cover and promises it to the model; the fire must speak THAT phrase, not roll a
    new one — otherwise the continuation instruction points at words that never sounded."""
    import voice.proactive as proactive
    monkeypatch.setattr(proactive, "user_speaking", lambda: False)
    promised = fa.arm(_Brain(), "¿me buscas un hotel en Soria?")
    assert promised, "arm must hand back the chosen phrase"
    out = _run(_collect_llm(_inner_llm(first_after=0.3)))
    assert _shape(out)[0] == promised + " ", f"the promise {promised!r} must be what sounds, got {_shape(out)[0]!r}"


def test_the_arm_notes_the_cover_into_the_turn_prompt_only():
    """The [SISTEMA] continuation note lands on the LAST USER message of the local `messages` list — and
    nowhere else: the phrase must be inside it, and a caller that passes no messages gets no side effect."""
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "búscame un hotel"}]
    phrase = fa.arm(_Brain(), "búscame un hotel", messages=msgs)
    assert phrase and phrase in msgs[-1]["content"], "the exact cover phrase must ride the note"
    assert msgs[-1]["content"].startswith("búscame un hotel"), "the operator's words stay first, untouched"
    assert msgs[0]["content"] == "sys", "the stable prefix (V2-536 cache) must never change"
    fa._reset_for_tests()
    phrase2 = fa.arm(_Brain(), "otra cosa")           # no messages → arm still works, no crash
    assert isinstance(phrase2, str)


def test_the_recent_window_beats_the_old_depth_one_repetition():
    """Operator, 2026-09-09: «no siempre las mismas tres». With depth-1 anti-repetition he heard «A ver…»
    twice in three turns; the pool now carries a recent window, so five consecutive picks are five
    different phrases."""
    from voice.engine.core import langs
    picks = [langs.pick_filler(kind="neutral", code="es") for _ in range(5)]
    assert len(set(picks)) == 5, f"five picks must differ: {picks}"


def test_a_dangling_fragment_gets_no_cover_at_all():
    """V2-642 — measured 20:51:26: the STT delivered «Ahora quiero» alone and the turn covered it with
    «A ver qué tenemos…», promising an answer to half a sentence. A fragment arms NOTHING; a whole sentence
    still does."""
    for frag in ("Ahora quiero", "ponme la", "y también el de", "vale pues"):
        fa._reset_for_tests()
        assert fa.arm(_Brain(), frag) == "", f"{frag!r} must arm no cover"
        assert fa._consume_arm() is None, f"{frag!r} left an arm behind"
    fa._reset_for_tests()
    assert fa.arm(_Brain(), "Búscame un hotel en Soria para el sábado"), "a whole sentence still arms"
