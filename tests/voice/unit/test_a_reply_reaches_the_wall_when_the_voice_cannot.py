"""The reply reaches the wall even when the voice cannot (V2-773, node 3.81).

Measured 2026-09-27 with Inworld out of credits (402 on every synthesis): LiveKit retried, gave up
(`tts_error`, recoverable=False) and never added the assistant item — and the assistant transcript is
emitted from `conversation_item_added`. The wall stayed blank while a worker started. What the voice is
fed is what the wall gets when the voice fails, marked so, and never twice.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from voice.engine.pipeline import reply_wall as rw

AGENT = Path("voice/engine/pipeline/agent.py")
ZAGENT = Path("voice/engine/pipeline/zaelar_agent.py")


@pytest.fixture(autouse=True)
def _clean():
    rw._cur.update({"parts": [], "t": 0.0})
    rw._shown.update({"text": "", "t": 0.0})


def _dead(recoverable=False, kind="tts_error"):
    return SimpleNamespace(type=kind, recoverable=recoverable, error=Exception("Connection error."))


def test_a_stream_is_remembered_and_handed_on_unchanged():
    async def _src():
        for c in ("I'm on a deep search ", "for three monitors."):
            yield c

    async def _go():
        return [c async for c in rw.tee(_src())]
    assert asyncio.run(_go()) == ["I'm on a deep search ", "for three monitors."]
    assert rw.pending_text() == "I'm on a deep search for three monitors."
    assert rw.tee("Hello there") == "Hello there" and rw.pending_text() == "Hello there"


def test_a_dead_voice_surfaces_the_reply_once_and_marks_it():
    rw.tee("I'm on a deep search for three monitors.")
    out = []
    emit = lambda *a, **k: out.append((a, k))
    assert rw.is_tts_dead(_dead()) is True
    assert rw.surface(emit) == "I'm on a deep search for three monitors."
    assert out and out[0][0] == ("transcript", "zaelar") and out[0][1]["role"] == "assistant"
    assert out[0][1]["extra"] == {"tts_failed": True}, "THE BUG: the wall must know this line was never heard"
    assert rw.surface(emit) == "" and len(out) == 1, "LiveKit's retries fire the error more than once"
    assert rw.already_surfaced("I'm on a deep search for three monitors.") is True, "if the item lands later, not twice"
    assert rw.already_surfaced("Something else") is False


def test_a_retry_is_not_a_dead_voice():
    assert rw.is_tts_dead(_dead(recoverable=True)) is False
    assert rw.is_tts_dead(_dead(kind="stt_error")) is False
    assert rw.is_tts_dead(Exception("plain")) is False
    rw.tee("")
    assert rw.surface(lambda *a, **k: (_ for _ in ()).throw(AssertionError("nothing to show"))) == ""


def test_the_session_wires_the_tee_and_the_two_hooks():
    """A seam nobody calls is the V2-741 shape. The tee sits where the voice is fed, the error hook surfaces,
    and the item hook defers to it."""
    z = ZAGENT.read_text(encoding="utf-8")
    assert "_rw.tee(text)" in z[z.index("def tts_node"):], "what the voice is fed goes through the tee"
    a = AGENT.read_text(encoding="utf-8")
    err = a[a.index('@session.on("error")'):]
    nxt = err.find("@session.on(", 1)
    err = err[:nxt if nxt > 0 else len(err)]
    assert "_reply_wall.is_tts_dead(_err)" in err and "_reply_wall.surface(_emit)" in err
    item = a[a.index('@session.on("conversation_item_added")'):]
    item = item[:item.index('@session.on("agent_false_interruption")')]
    assert "not _reply_wall.already_surfaced(text)" in item, "the late item must not paint the line twice"
