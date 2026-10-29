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
    monkeypatch.setitem(lag._state, "loops", set())
    return seen


def test_a_blocked_voice_loop_is_measured_said_and_sheds_load(acts, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")

    async def session():
        lag.watch()
        await asyncio.sleep(0.05)
        time.sleep(1.2)                      # the loop is held: what a starved host does to the voice
        await asyncio.sleep(0.3)
    asyncio.run(session())
    assert any(e.get("kind_diag") == "voice_lag" and e.get("lag_s", 0) >= 0.2 for e in acts["events"]), acts
    assert acts["shed"], "the lag did not shed background work"
    assert acts["notices"] and len(acts["notices"]) == 1, f"one notice per cooldown: {acts['notices']}"


def test_a_voice_on_time_does_nothing(acts):
    assert lag.note(0.05, "voice_loop") is False and not acts["events"] and not acts["shed"]


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
