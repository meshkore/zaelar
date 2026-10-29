"""The voice measures its own lag and acts (V2-831 T-30).

On the operator's cloud host the voice went deaf in stretches that lined up with errands: VAD inference fell behind
real time and the job executor missed its pings — two LOG LINES nothing read. Now the session's own loop is probed,
the SDK's measured `delay` fields are read, and over the declared bound (`voice_lag_s`) the engine says so: an event,
one spoken notice in his language, and load shed through the worker envelope (T-27).

Disarm: make `lag.note` never act → red.
"""
from __future__ import annotations

import asyncio
import logging
import time

import pytest

from voice import lag


@pytest.fixture
def acts(monkeypatch):
    from nucleo.workers import envelope
    from voice import observer, proactive
    seen = {"events": [], "notices": [], "shed": []}
    monkeypatch.setattr(envelope, "policy", lambda: {**envelope._DEFAULTS, "voice_lag_s": 0.2})
    monkeypatch.setattr(observer, "emit", lambda kind, label, **k: seen["events"].append(k.get("extra") or {}))

    async def notify(title, text, **k):
        seen["notices"].append(text)
    monkeypatch.setattr(proactive, "notify", notify)
    monkeypatch.setattr(envelope, "shed", lambda s: seen["shed"].append(s))
    monkeypatch.setitem(lag._state, "last_act", -1e9)
    monkeypatch.setitem(lag._state, "episode", False)
    monkeypatch.setitem(lag._state, "loops", set())
    monkeypatch.setattr(lag, "_audio_flows", lambda: seen["audio"])
    monkeypatch.setattr(proactive, "user_speaking", lambda: seen["speaking"])
    seen.update(audio=True, speaking=True)
    return seen


def test_a_blocked_loop_in_a_typed_session_sheds_quietly(acts, monkeypatch):
    """Pass 10 on v3.107: the loop lag of our own heavy turns, mic off, was said six times as «I'm running behind».
    The loop's own lag is not the audio path: it sheds load quietly — no event, no words."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    acts.update(audio=False, speaking=False)

    async def session():
        lag.watch()
        await asyncio.sleep(0.05)
        time.sleep(1.2)                      # the loop is held by our own work
        await asyncio.sleep(0.3)
    asyncio.run(session())
    assert acts["shed"], "the loop lag still sheds, internally"
    assert not acts["events"] and not acts["notices"], (acts["events"], acts["notices"])


def test_the_audio_path_falling_behind_while_he_talks_is_said_once(acts, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")

    async def go():
        lag.note(1.2, "vad.py")
        await asyncio.sleep(0)
    asyncio.run(go())
    assert any(e.get("kind_diag") == "voice_lag" for e in acts["events"]) and acts["shed"]
    assert len(acts["notices"]) == 1


def test_no_audio_flowing_means_no_voice_lag(acts):
    acts["audio"] = False
    assert lag.note(1.2, "vad.py") is False and not acts["events"] and not acts["notices"]


def test_a_lag_while_he_is_silent_is_an_event_not_words(acts, monkeypatch):
    acts["speaking"] = False

    async def go():
        lag.note(1.2, "job_thread_executor.py")
        await asyncio.sleep(0)
    asyncio.run(go())
    assert acts["events"] and acts["shed"] and not acts["notices"]


def test_a_voice_on_time_does_nothing(acts):
    assert lag.note(0.05, "vad.py") is False and not acts["events"] and not acts["shed"]


def test_the_sdks_measured_delays_are_read_from_the_record_not_its_words(acts, monkeypatch):
    got = []
    monkeypatch.setattr(lag, "note", lambda s, src: got.append((round(s, 2), src)))
    h = lag._SdkDelays()
    for fn, delay in (("vad.py", 1.2), ("job_thread_executor.py", 2000)):
        rec = logging.LogRecord("livekit.agents", logging.WARNING, fn, 1, "any words at all", None, None)
        rec.delay = delay
        h.emit(rec)
    assert got == [(1.2, "vad.py"), (2.0, "job_thread_executor.py")], got


def test_a_shed_holds_new_workers_and_pauses_the_newest(monkeypatch):
    from types import SimpleNamespace
    from nucleo.workers import envelope
    monkeypatch.setattr(envelope, "measured", lambda: (8, 8))            # plenty of memory: only the shed acts
    monkeypatch.setitem(envelope._shed, "until", 0.0)

    class S:
        def __init__(self, r): self.r = r
        def pause(self): self.r.paused = True; return True    # noqa: E702
        def resume(self): self.r.paused = False; return True  # noqa: E702
    a = SimpleNamespace(task_id="1", status="running", started=1, paused=False)
    b = SimpleNamespace(task_id="2", status="running", started=2, paused=False)
    a.session, b.session = S(a), S(b)
    envelope.shed(30)
    assert envelope.shedding() and envelope.relieve([a, b]) == "paused 2"


def test_the_live_session_is_what_gets_measured():
    """Only the LIVE session's speaker starts the probe — a test or a typed channel registering one does not."""
    import inspect
    from voice.engine.pipeline import agent
    assert "register_speaker(_speak, watch_lag=True)" in inspect.getsource(agent)


def test_the_notice_is_said_once_per_episode_and_again_after_recovery(acts, monkeypatch):
    """A lag that persists across cooldowns is said ONCE; it is said again only after it recovered and came back."""
    async def go():
        lag.note(0.9, "vad.py")                        # an episode starts: said
        lag._state["last_act"] = -1e9                  # a cooldown later, still lagging
        lag.note(0.9, "vad.py")                        # acts (event + shed), not said again
        lag.note(0.05, "vad.py")                       # recovered
        lag._state["last_act"] = -1e9
        lag.note(0.9, "vad.py")                        # a NEW episode: said again
        await asyncio.sleep(0)
    asyncio.run(go())
    assert len(acts["notices"]) == 2, acts["notices"]
    assert len(acts["shed"]) == 3


def test_audio_flows_only_with_a_live_input_that_feeds_the_recogniser(monkeypatch):
    from voice import mic_input
    monkeypatch.setitem(mic_input._input, "sink", None)
    monkeypatch.setattr(mic_input, "feeds_stt", lambda: True)
    assert mic_input.hears() is False, "no live voice session holds the input (a typed session)"
    monkeypatch.setitem(mic_input._input, "sink", lambda on: None)
    assert mic_input.hears() is True
    monkeypatch.setattr(mic_input, "feeds_stt", lambda: False)
    assert mic_input.hears() is False, "the microphone is off"
