"""One say that never confirms its playout no longer wedges every later delivery (V2-831 T-19 R13).

Demo sandbox build 86, pass 2. At 1111 s a hard close spoke its receipt («Nothing's left on screen.») from INSIDE
the voice turn and awaited the say's playout. That say was queued behind the turn's own speech, which could not end
until the receipt returned — a circular wait. The session sat in «thinking» from then on, and no later say ever
reported done. `proactive.notify` awaited each say with no bound while holding the delivery ticket, so every later
delivery (cron, workers, the circuit, a turn's follow-up) waited the queue's 180 s and degraded to a next-turn note.

Two halves, each with its test:
  · the queue: a say is awaited on a clock tied to its own length; past it the delivery is reported UNCONFIRMED and
    the ticket moves on, so the next delivery goes out;
  · the cause: a say issued from inside a speech's own generation is scheduled, never awaited.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from tests.waiting import until
from voice import brain_notes, proactive


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    seen: list = []
    monkeypatch.setattr("voice.observer.emit", lambda kind, label, **k: seen.append((kind, label, k)))
    monkeypatch.setattr(proactive, "_SAY_MARGIN_S", 0.3)        # a bound of ~0.3 s + length, not seconds
    monkeypatch.setattr(proactive, "_SAY_CHARS_PER_S", 400.0)
    monkeypatch.setattr(proactive, "_BOT_GRACE_SECS", 0.0)
    brain_notes.drain()
    proactive._reset_queue_for_tests()
    yield seen
    proactive.clear_speaker()
    brain_notes.drain()
    proactive._reset_queue_for_tests()


def test_the_bound_follows_the_says_own_length():
    short, long = proactive.say_bound("Done."), proactive.say_bound("x" * 400)
    assert short < long and long - short == pytest.approx(395 / proactive._SAY_CHARS_PER_S)


def test_a_say_that_never_completes_releases_the_queue(_isolated):
    stuck = asyncio.Event()                      # never set: the playout confirmation that never comes
    said: list[str] = []

    async def _speaker(text):
        said.append(text)
        if text.startswith("first"):
            await stuck.wait()
    proactive.register_speaker(_speaker)

    async def _go():
        t0 = time.monotonic()
        a = asyncio.create_task(proactive.notify("t1", "first delivery, whose say never confirms"))
        await asyncio.sleep(0.02)
        b = asyncio.create_task(proactive.notify("t2", "second delivery"))
        await until(lambda: "second delivery" in said, "the next delivery to go out behind the stuck say",
                    timeout_s=5.0)
        took = time.monotonic() - t0
        ra, rb = await asyncio.gather(a, b)
        return took, ra, rb
    took, ra, rb = asyncio.run(_go())
    assert took < proactive.say_bound("first delivery, whose say never confirms") + 2.0
    assert ra is False and rb is True, "the unconfirmed say is not reported as said; the next one is"
    errors = [lbl for kind, lbl, _ in _isolated if kind == "error"]
    assert any("SIN CONFIRMAR" in x for x in errors), "an unconfirmed say is logged, never silent"
    assert not brain_notes.drain(), "the say may still play: it is not ALSO parked as a note for a later turn"


class _Handle:
    """A LiveKit SpeechHandle stand-in: awaiting it waits for a playout that this test controls."""

    def __init__(self, done=False):
        self._fut = None
        self._done = done

    def done(self):
        return self._done

    def __await__(self):
        async def _w():
            await asyncio.Event().wait()          # never confirms
        return _w().__await__()


def _speak_inside(owner_done: bool):
    from livekit.agents.voice.agent_activity import _SpeechHandleContextVar
    from voice.engine.pipeline import agent_events
    events: list = []

    class _Session:
        def say(self, text, **k):
            return _Handle()

    async def _on_loop(fn):
        return await fn()

    async def _go():
        tok = _SpeechHandleContextVar.set(_Handle(done=owner_done))   # we run inside this speech's generation
        try:
            await asyncio.wait_for(agent_events._speak(
                "Nothing's left on screen.", _busy={"bot": False, "user": False},
                _emit=lambda kind, label, **k: events.append(label), _on_session_loop=_on_loop, session=_Session()),
                timeout=1.0)
            return True, events
        except asyncio.TimeoutError:
            return False, events
        finally:
            _SpeechHandleContextVar.reset(tok)
    return asyncio.run(_go())


def test_a_say_from_inside_a_turn_is_scheduled_not_awaited():
    returned, events = _speak_inside(owner_done=False)
    assert returned, "a say awaited from inside the speech it queues behind is a circular wait — it wedged the session"
    assert any("PROGRAMADA" in x for x in events) and not any("COMPLETADA" in x for x in events)


def test_outside_a_live_speech_the_say_is_still_awaited():
    returned, events = _speak_inside(owner_done=True)
    assert not returned, "with no speech in flight the say's playout is awaited as before"
