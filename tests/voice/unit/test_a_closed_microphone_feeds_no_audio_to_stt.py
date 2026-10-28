"""V2-831 T-18 — no closed state feeds a single frame to the speech recogniser (node 3.150).

THE CLASS. A cloud STT bills every frame it is PUSHED (the Deepgram plugin reports usage per 5 s of pushed audio,
`PeriodicCollector(duration=5.0)`). The microphone switch acted only AFTER transcription (`mic_input.blocks_turn`
discards the turn), so with the mic closed, the agent stopped (⏻) or the tap parked for the wake word, the
session's audio input kept handing frames to the STT: one usage report per 5 s of audio, 12 a minute, for
silence — including a session that reconnects with the mic already closed.

THE DOOR. `voice/mic_input.py::feeds_stt()` = not muted, not parked, not stopped; every write re-applies it to
the session's audio INPUT (`session.input.set_audio_enabled`), installed by
`voice/engine/pipeline/agent_events.py::open_mic_door`.

What runs here is REAL `livekit.agents` code end to end except the network: the session's `AgentInput` (the lever
the door pulls) over the real room input `room_io._ParticipantAudioInputStream`, whose own `_forward_task` drops
frames while detached, fed real `rtc.AudioFrame`s by a stand-in for the remote track. Downstream, what
`AgentSession._forward_audio_task` does (`async for frame in audio_input`) feeds a counting STT that bills every
5 s of pushed audio through the REAL `metrics_tap.on_metrics` → `report_stt_usage`.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from livekit import rtc
from livekit.agents.voice import io as lk_io
from livekit.agents.voice.room_io._input import _ParticipantAudioInputStream

from tests.waiting import until
from voice import mic_input
from voice.engine.pipeline import agent_events, metrics_tap

RATE, FRAME_S = 24000, 0.02
_NOEMIT = lambda *a, **k: None  # noqa: E731


class FakeRoom:
    remote_participants: dict = {}

    def on(self, *_a, **_k):
        return None

    def off(self, *_a, **_k):
        return None


class RemoteTrack:
    """The subscribed microphone: an endless stream of 20 ms frames, delivered when he speaks. A muted remote
    publication still delivers frames at the agent — which is why the browser's mute alone is not enough."""

    def __init__(self) -> None:
        self.q: asyncio.Queue = asyncio.Queue()

    def __aiter__(self):
        return self

    async def __anext__(self):
        return SimpleNamespace(frame=await self.q.get())


class CountingSTT:
    """A cloud STT: counts frames, and reports usage every 5 s of pushed audio like the Deepgram plugin."""

    def __init__(self, bill) -> None:
        self.frames, self._acc, self._bill = 0, 0.0, bill

    def push(self, dur: float) -> None:
        self.frames += 1
        self._acc += dur
        if self._acc >= 5.0 - 1e-9:
            self._bill(self._acc)
            self._acc = 0.0


class Session:
    """The parts of `AgentSession` the door touches: its real `AgentInput`, and `on("close")`."""

    def __init__(self) -> None:
        self.input = lk_io.AgentInput(video_changed=lambda: None, audio_changed=lambda: None)
        self._close: list = []
        self.calls: list[bool] = []
        real = self.input.set_audio_enabled

        def counted(v):
            self.calls.append(bool(v))
            real(v)
        self.input.set_audio_enabled = counted

    def on(self, event, cb=None):
        if event == "close":
            self._close.append(cb)
        return cb

    def close(self):
        for cb in self._close:
            cb(None)


class Rig:
    def __init__(self, usage) -> None:
        self.usage = usage
        self.session = Session()
        self.room_input: _ParticipantAudioInputStream | None = None
        self.stt = CountingSTT(self._bill)
        self._tasks: list[asyncio.Task] = []

    def _bill(self, seconds: float) -> None:
        m = type("STTMetrics", (), {"duration": 0.1, "audio_duration": seconds})()
        metrics_tap.on_metrics(SimpleNamespace(metrics=m), _NOEMIT)

    def attach_room_input(self) -> None:
        """What `session.start(room=…)` does: mount the room input and start reading the remote track."""
        self.room_input = _ParticipantAudioInputStream(
            FakeRoom(), sample_rate=RATE, num_channels=1, noise_cancellation=None,
            auto_gain_control=False, pre_connect_audio_handler=None)
        self.session.input.audio = self.room_input
        self.track = RemoteTrack()
        pub = SimpleNamespace(source=rtc.TrackSource.SOURCE_MICROPHONE, audio_features=[], track=None)
        self._tasks.append(asyncio.ensure_future(self.room_input._forward_task(
            None, self.track, pub, SimpleNamespace(identity="him"))))
        self._tasks.append(asyncio.ensure_future(self._downstream()))

    async def _downstream(self) -> None:
        async for frame in self.room_input:   # AgentSession._forward_audio_task → activity.push_audio → STT
            self.stt.push(frame.duration)

    async def speak(self, seconds: float = 12.0) -> None:
        for _ in range(round(seconds / FRAME_S)):
            self.track.q.put_nowait(rtc.AudioFrame.create(RATE, 1, int(RATE * FRAME_S)))
        await until(self.track.q.empty, "the room input to read every frame the track delivered", timeout_s=10)
        await asyncio.sleep(0.02)   # the last frame's hop: room input → channel → STT

    async def aclose(self) -> None:
        self.session.close()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)


@pytest.fixture
def env(monkeypatch):
    """Running agent, cloud STT selected, billing counted, a clean switch before and after."""
    from nucleo import runstate
    from nucleo.energy import meter
    from voice.engine.core.config import SETTINGS

    mic_input.reset()
    monkeypatch.setitem(runstate._state, "value", runstate.RUNNING)
    monkeypatch.setattr(metrics_tap, "SETTINGS", dataclasses.replace(SETTINGS, stt_provider="deepgram"))
    usage: list[float] = []
    monkeypatch.setattr(meter, "report_stt_usage",
                        lambda audio_seconds=None, provider=None: usage.append(audio_seconds))
    yield SimpleNamespace(usage=usage, runstate=runstate, monkeypatch=monkeypatch)
    mic_input.reset()


def live(env, body):
    """Run `body(rig)` inside a live session: the door installed ON the session's loop before the room input is
    mounted — the entrypoint's order (`open_mic_door` before `session.start`)."""
    async def main():
        rig = Rig(env.usage)
        agent_events.open_mic_door(session=rig.session)
        rig.attach_room_input()
        try:
            await body(rig)
        finally:
            await rig.aclose()
    asyncio.run(main())


def _packet(topic, body):
    return SimpleNamespace(topic=topic, data=json.dumps(body).encode())


# ── the baseline that makes every zero below mean something ──────────────────────────────────────────────────

def test_an_open_microphone_feeds_the_stt_and_bills_once_per_five_seconds(env):
    async def body(rig):
        await rig.speak(60.0)
        assert rig.stt.frames == 3000, rig.stt.frames
        assert len(rig.usage) == 12, f"one Deepgram charge per 5 s of audio = 12/min, got {len(rig.usage)}"
    live(env, body)


# ── the three closed states: 0 frames, 0 charges ─────────────────────────────────────────────────────────────

def test_a_closed_microphone_feeds_zero_frames_and_bills_nothing(env):
    async def body(rig):
        mic_input.set_muted(True, source="orb")
        await rig.speak(60.0)
        assert rig.stt.frames == 0, f"a closed mic pushed {rig.stt.frames} frames into the STT"
        assert rig.usage == [], f"a closed mic was billed: {rig.usage}"
        mic_input.set_muted(False, source="orb")
        await rig.speak(12.0)
        assert rig.stt.frames > 0 and rig.usage, "reopening must give the ear back, or the cure is deafness"
    live(env, body)


def test_power_off_feeds_zero_frames_even_without_a_mic_write(env):
    """⏻ stopped from anywhere (another screen, the server): the next heartbeat re-asserts the switch with the
    SAME value and that alone closes the input — the stop is part of the rule, not of the button."""
    async def body(rig):
        env.monkeypatch.setitem(env.runstate._state, "value", env.runstate.STOPPED)
        mic_input.set_muted(False, source="heartbeat")
        await rig.speak(60.0)
        assert rig.stt.frames == 0 and rig.usage == [], (rig.stt.frames, rig.usage)
        env.monkeypatch.setitem(env.runstate._state, "value", env.runstate.RUNNING)
        mic_input.set_muted(False, source="heartbeat")
        await rig.speak(12.0)
        assert rig.stt.frames > 0, "⏻ on must open the input again"
    live(env, body)


def test_a_tap_waiting_for_the_wake_word_feeds_zero_frames(env):
    """The browser parks its track while the free ear listens for the name and says so on `zaelar-tap`;
    driven through the REAL data handler with the packet the browser publishes."""
    async def body(rig):
        agent_events._on_data(_packet("zaelar-tap", {"t": "zaelar-tap", "parked": True}),
                              _emit=_NOEMIT, _json=json, _wake={}, session=rig.session)
        await rig.speak(60.0)
        assert rig.stt.frames == 0 and rig.usage == [], (rig.stt.frames, rig.usage)
        agent_events._on_data(_packet("zaelar-tap", {"t": "zaelar-tap", "parked": False}),
                              _emit=_NOEMIT, _json=json, _wake={}, session=rig.session)
        await rig.speak(12.0)
        assert rig.stt.frames > 0, "unparking must open the input"
    live(env, body)


def test_a_spotted_wake_word_opens_the_input_even_if_the_unpark_was_lost(env):
    async def body(rig):
        mic_input.set_parked(True)
        agent_events._on_data(_packet("zaelar-wake", {"t": "zaelar-wake", "phase": "spot", "text": "", "before": ""}),
                              _emit=_NOEMIT, _json=json, _wake={"spot_at": 0.0}, session=rig.session)
        await rig.speak(1.0)
        assert rig.stt.frames > 0, "the sentence behind the name must be heard"
    live(env, body)


# ── the reconnect: a session born with the mic closed ─────────────────────────────────────────────────────────

def test_a_session_born_with_the_microphone_closed_never_feeds_a_frame(env):
    """The mic was closed BEFORE the session existed. The first frame the track ever delivers is already
    dropped — no window opens while waiting for the first heartbeat."""
    mic_input.set_muted(True, source="orb")

    async def body(rig):
        assert rig.session.input.audio_enabled is False
        await rig.speak(0.02)
        assert rig.stt.frames == 0, "the very first frame of a reconnect reached the STT"
        await rig.speak(30.0)
        assert rig.stt.frames == 0 and rig.usage == []
    live(env, body)


def test_a_new_session_starts_unparked_but_keeps_the_mute(env):
    """Park is a transport fact of ONE browser session (a stale one would leave the agent deaf); mute is the
    operator's hand and stays."""
    mic_input.set_parked(True)

    async def body(rig):
        assert rig.session.input.audio_enabled is True
        mic_input.set_muted(True, source="orb")
    live(env, body)
    assert mic_input.is_muted() is True


# ── the heartbeat must not flap ──────────────────────────────────────────────────────────────────────────────

def test_a_heartbeat_that_changes_nothing_does_not_touch_the_input(env):
    async def body(rig):
        assert rig.session.calls == [True], rig.session.calls      # the install applies once
        for _ in range(30):
            mic_input.set_muted(False, source="heartbeat")
        assert rig.session.calls == [True], "an idempotent beat must not re-pull the lever"
        mic_input.set_muted(True, source="orb")
        for _ in range(30):
            mic_input.set_muted(True, source="heartbeat")
            mic_input.set_parked(False)
        assert rig.session.calls == [True, False], rig.session.calls
    live(env, body)


# ── ownership and threads ────────────────────────────────────────────────────────────────────────────────────

def test_a_closed_session_uninstalls_only_its_own_door(env):
    async def main():
        old, new = Session(), Session()
        agent_events.open_mic_door(session=old)
        agent_events.open_mic_door(session=new)   # the voice moved
        old.close()
        mic_input.set_muted(True, source="orb")
        assert new.input.audio_enabled is False, "the old session's close must not unhook the live one"
        new.close()
    asyncio.run(main())


def test_a_write_from_another_thread_lands_on_the_session_loop(env):
    """The switch is written from HTTP routes; the input belongs to the session's loop."""
    async def body(rig):
        seen: list = []
        orig = rig.session.input.set_audio_enabled

        def spy(v):
            try:
                seen.append(asyncio.get_running_loop())
            except RuntimeError:
                seen.append(None)
            orig(v)
        rig.session.input.set_audio_enabled = spy
        t = threading.Thread(target=lambda: mic_input.set_muted(True, source="api"))
        t.start(); t.join()
        await asyncio.sleep(0.05)
        assert rig.session.input.audio_enabled is False
        assert seen and seen[-1] is asyncio.get_running_loop(), "moved from the route's thread"
        await rig.speak(5.0)
        assert rig.stt.frames == 0
    live(env, body)


# ── the wiring: the entrypoint really installs the door, before the session starts ───────────────────────────

def test_the_entrypoint_installs_the_door_before_the_session_starts():
    src = (Path(__file__).resolve().parents[3] / "voice" / "engine" / "pipeline" / "agent.py").read_text("utf-8")
    i, j = src.find("_agent_events.open_mic_door(session=session"), src.find("await session.start(")
    assert i > 0, "the entrypoint never installs the input door: every closed state would bill again"
    assert i < j, "installed after session.start, the first frames of a closed-mic reconnect would be billed"
