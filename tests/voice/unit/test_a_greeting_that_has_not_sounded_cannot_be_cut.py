"""V2-745 — a reply that has not made a sound cannot be interrupted, and the veil waits for the sound.

## The session

`8fc3e1c9` (2026-09-21), the operator's own, a brand-new agent from power-on:

    +1.06 s  kickoff dispatched
    +4.04 s  reply generated («¡Hola! Soy Zaelar, tu asistente personal. ¿Cómo te llamas?»)
    +4.07 s  🎤 VAD on, `over_agent: false`   ← four seconds of silence, so he said «¿Qué pasa?»
    +4.62 s  TTSMetrics: 6.77 s of audio SYNTHESISED
    +4.63 s  bot_speech → IDLE, and no `speaking` edge anywhere before it

Six seconds of speech generated, paid for and thrown away 30 ms after the text existed. The first thing he
ever heard was a filler at +22 s, after two more turns of his were ruled ambient. His words:

    «No deberíamos dar acceso a la gente hasta que eso estuviera totalmente inicializado y operativo…
     hay que controlar que todos los servicios estén activos, porque si no, el primer usuario que lo
     pruebe SE PASARÁ DIEZ SEGUNDOS HABLANDO CONTRA UNA PARED y pensará que no [funciona].»

## What is measured here

`first_air.py` is the whole decision and it has no LiveKit in it, so these drive the REAL object rather
than a copy — and the last group reads `agent.py`'s source, because mounting the session needs half a
LiveKit stack (the same reason `test_agent_trace_source_guards.py` gives) and a double proves the mapping
and never the wiring.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from voice.engine.pipeline.first_air import READY_MAX_S, FirstAir

SRC = Path(__file__).resolve().parents[3] / "voice/engine/pipeline/agent.py"


class _Handle:
    """What `session.generate_reply` hands back, as far as this decision is concerned."""

    def __init__(self, allow: bool = True) -> None:
        self.allow_interruptions = allow


def _air(**kw):
    lifts = []
    return FirstAir(ready=lambda: lifts.append(1), **kw), lifts


# ── the greeting ──────────────────────────────────────────────────────────────────────────────────────

def test_a_parked_greeting_stays_uninterruptible_until_it_sounds():
    air, _ = _air()
    h = _Handle(allow=False)                       # created with interruptions off — the whole point
    air.park(h)
    assert h.allow_interruptions is False, "nothing has sounded yet: a barge-in here cuts silence"


def test_the_first_audio_frame_hands_the_interruption_back():
    """He must still be able to cut a greeting he is HEARING — that is what the gesture means, and it is
    the half that must not be lost to the fix."""
    air, _ = _air()
    h = _Handle(allow=False)
    air.park(h)
    air.on_speaking()
    assert h.allow_interruptions is True


def test_a_handle_that_refuses_the_flip_does_not_take_the_session_down():
    """Already interrupted, or an older handle: LiveKit raises on that setter, and a greeting is not worth
    a dead session."""
    class _Stubborn:
        @property
        def allow_interruptions(self):
            return False

        @allow_interruptions.setter
        def allow_interruptions(self, v):
            raise RuntimeError("already interrupted")

    air, lifts = _air()
    air.park(_Stubborn(), on_air=air.lift)
    air.on_speaking()
    assert lifts == [1], "…and the veil still lifts: the sound happened, whatever the handle says"


def test_a_later_speaking_edge_carries_nothing_and_changes_nothing():
    air, lifts = _air()
    h = _Handle(allow=False)
    air.park(h, on_air=air.lift)
    air.on_speaking()
    air.on_speaking()                              # every subsequent reply of the session
    assert lifts == [1], "the barrier is published ONCE"


# ── the boot veil ─────────────────────────────────────────────────────────────────────────────────────

def test_the_veil_lifts_on_the_first_audio_frame_and_not_before():
    air, lifts = _air()
    air.park(_Handle(allow=False), on_air=air.lift)
    assert lifts == [], ("THE BUG: the splash imploded at +0.8 s and the greeting never came — «no "
                         "deberíamos dar acceso hasta que estuviera totalmente inicializado y operativo»")
    air.on_speaking()
    assert lifts == [1]


def test_lifting_is_idempotent_so_every_silent_path_may_call_it():
    air, lifts = _air()
    air.lift(); air.lift(); air.on_speaking()
    assert lifts == [1] and air.lifted is True


def test_a_barrier_whose_publish_throws_still_counts_as_lifted():
    """A stranded splash is the worst outcome available here, so the failure direction is «lift anyway»."""
    def _boom():
        raise RuntimeError("room gone")

    air = FirstAir(ready=_boom)
    air.lift()
    assert air.lifted is True


def test_a_greeting_that_never_sounds_still_lifts_the_veil():
    """BOUNDED, and the bound is the point: the client's own 60 s net chose this direction first."""
    air, lifts = _air()
    air.park(_Handle(allow=False), on_air=air.lift)
    asyncio.run(air._net(0.02))
    assert lifts == [1]


def test_the_safety_net_does_not_lift_a_veil_that_already_went_up():
    air, lifts = _air()
    air.park(_Handle(allow=False), on_air=air.lift)
    air.on_speaking()
    asyncio.run(air._net(0.02))
    assert lifts == [1], "a second publish would re-show and re-implode the splash"


def test_the_safety_net_survives_its_own_cancellation():
    air, lifts = _air()

    async def _drive():
        task = air.arm_safety_net(seconds=30)
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_drive())
    assert lifts == [], "a torn-down session publishes nothing"


def test_the_bound_is_generous_enough_for_the_cold_handshake_we_measured():
    assert READY_MAX_S >= 8.0, (
        "the first model call of a session paid TTFT 2.43 s plus 0.63 s of TTS ttfb on his own machine; a "
        "bound under that would lift the veil onto the very silence this exists to remove")


# ── the wiring: `agent.py` must actually be using it ──────────────────────────────────────────────────

def _body() -> str:
    return SRC.read_text(encoding="utf-8")


def test_the_kickoff_is_created_uninterruptible_and_parked():
    body = _body()
    assert "generate_reply(user_input=kickoff_text, allow_interruptions=False)" in body, (
        "the greeting must be born uninterruptible, or the barge-in that killed it at +4.07 s kills it again")
    assert "_air.park(_greeting, on_air=_air.lift)" in body, (
        "…and parked, or nothing ever hands the interruption back and he cannot cut a greeting he hears")


def test_the_speaking_edge_is_what_releases_it():
    body = _body()
    i = body.index("def on_state_change(state: State) -> None:")
    block = body[i:body.index("\n    sm = StateMachine(", i)]
    assert "if speaking:" in block and "_air.on_speaking()" in block


def test_the_barrier_is_no_longer_published_before_the_greeting():
    """The regression that would restore the whole defect in one line."""
    body = _body()
    assert "boot.ready()" not in body, (
        "the barrier must go through `_air.lift()`, which is what ties it to the first audio frame")
    assert body.index("_air.arm_safety_net()") < body.index("kickoff_text = greeting_prompt(_lang)"), (
        "the net has to be armed before the greeting is attempted, or a failure strands the splash")


def test_every_path_that_will_not_greet_lifts_the_veil_at_once():
    """Three of them, and each one is a screen that would otherwise hang: a silent first run, a duplicate
    job for the same room, and a reconnection to a conversation already in progress."""
    body = _body()
    assert body.count("_air.lift()") == 3, "one per silent path: onboarding, duplicate job, resumed session"
    assert "on_air=_air.lift" in body, "…and the greeting's own, which fires on the first audio frame"
    for anchor in ("kickoff en silencio", "kickoff duplicado evitado", "kickoff omitido"):
        i = body.index(anchor)
        assert "_air.lift()" in body[i:i + 420], f"«{anchor}» leaves the splash up for ever"
