"""Proactive messages leave ONE AT A TIME, in arrival order — the operator's spec, verbatim (2026-08-31):

    «tiene que tener un buffer de un mensaje que le quiere lanzar y cuando ya se lo ha explicado le manda
     otro … si hay dos tareas a la vez y terminan simultáneamente, primero se informará al usuario de una
     tarea y después de la segunda.»

Until this queue, NOTHING serialized concurrent notifies: each waited for quiet on its own, two workers
finishing in the same instant both saw silence, and both called `session.say` — order and overlap were
LiveKit's internal scheduling, not a decision of ours. The V2-047 F7 instrumentation had already named the fix
(«el fix es SERIALIZAR») and stayed telemetry-only.

The queue is cross-LOOP on purpose (tickets + threading.Condition, entered via `asyncio.to_thread`): notifies
arrive from whatever loop their caller runs on — uvicorn workers, the orchestrator, messaging — and an
`asyncio.Lock` binds to one loop, which is exactly the «attached to a different loop» family this file just got
cured of. And a message never dies waiting: it degrades to the same `[SISTEMA]` note as always and abandons its
ticket, so the queue cannot wedge behind a slot nobody will fill.
"""
import asyncio
import threading
import time

import pytest

from voice import brain_notes, proactive


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """No observer (the UI emit is not under test and must not touch the real timeline), a drained mailbox, and
    a queue starting from ticket zero."""
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)
    brain_notes.drain()
    proactive._reset_queue_for_tests()
    yield
    proactive.clear_speaker()
    brain_notes.drain()
    proactive._reset_queue_for_tests()


class _RecordingSpeaker:
    """A speaker that takes real time, and records intervals — overlap is measurable, not inferred."""

    def __init__(self, secs=0.15):
        self.secs = secs
        self.intervals = []   # (text, start, end)

    async def __call__(self, text):
        t0 = time.monotonic()
        await asyncio.sleep(self.secs)
        self.intervals.append((text, t0, time.monotonic()))


def test_two_simultaneous_finishes_speak_one_at_a_time_in_arrival_order():
    """The exact scenario dictated: two tasks end at once. One message, THEN the other — no overlap ever."""
    spk = _RecordingSpeaker()
    proactive.register_speaker(spk)

    async def _drive():
        a = asyncio.create_task(proactive.notify("t1", "terminó la primera tarea"))
        await asyncio.sleep(0.01)          # arrival order is part of the contract, so make it unambiguous
        b = asyncio.create_task(proactive.notify("t2", "terminó la segunda tarea"))
        await asyncio.gather(a, b)

    asyncio.run(_drive())
    assert [t for t, *_ in spk.intervals] == ["terminó la primera tarea", "terminó la segunda tarea"], \
        "arrival order is the contract — whichever finished first is told first"
    (_, _, end1), (_, start2, _) = spk.intervals
    assert start2 >= end1, "the second message started while the first was still being spoken"


def test_deliveries_from_two_different_loops_still_serialize():
    """The real topology: workers deliver from uvicorn's loop, the session speaks on LiveKit's. An asyncio.Lock
    would blow up here; the ticket queue must not care."""
    spk = _RecordingSpeaker()
    proactive.register_speaker(spk)
    threads = [threading.Thread(target=lambda i=i: asyncio.run(proactive.notify(f"t{i}", f"mensaje {i}")))
               for i in range(3)]
    for t in threads:
        t.start()
        time.sleep(0.02)
    for t in threads:
        t.join(timeout=10)
    assert len(spk.intervals) == 3
    for (_, _, e1), (_, s2, _) in zip(spk.intervals, spk.intervals[1:]):
        assert s2 >= e1, "two loops, one voice: the queue is what keeps them from talking at once"


def test_a_message_that_cannot_get_the_floor_degrades_to_a_note_and_is_never_lost(monkeypatch):
    """A finish that queues behind a long explanation and runs out of budget becomes the same [SISTEMA] note as
    always — the FlashBrain says it itself next turn. Silence-drop would be the worst outcome."""
    monkeypatch.setattr(proactive, "_QUEUE_MAX_WAIT", 0.05)
    spk = _RecordingSpeaker(secs=0.6)
    proactive.register_speaker(spk)

    async def _drive():
        a = asyncio.create_task(proactive.notify("t1", "la explicación larga"))
        await asyncio.sleep(0.01)
        b = asyncio.create_task(proactive.notify("t2", "la tarea impaciente"))
        await asyncio.gather(a, b)

    asyncio.run(_drive())
    assert [t for t, *_ in spk.intervals] == ["la explicación larga"]
    notes = [t for _, t in getattr(brain_notes, "_pending", [])] or brain_notes.drain()
    assert any("la tarea impaciente" in n for n in notes), \
        "a message that lost its slot has to reach the brain as a note — never vanish"


def test_an_abandoned_ticket_does_not_wedge_the_queue(monkeypatch):
    """Whoever gives up must not leave a turn nobody will take: the NEXT delivery still speaks."""
    monkeypatch.setattr(proactive, "_QUEUE_MAX_WAIT", 0.05)
    spk = _RecordingSpeaker(secs=0.4)
    proactive.register_speaker(spk)

    async def _drive():
        a = asyncio.create_task(proactive.notify("t1", "primera"))
        await asyncio.sleep(0.01)
        b = asyncio.create_task(proactive.notify("t2", "la que abandona"))
        await asyncio.gather(a, b)
        # arrives AFTER the abandonment: its turn must come even though a ticket in between was never served
        await proactive.notify("t3", "la de después")

    asyncio.run(_drive())
    assert [t for t, *_ in spk.intervals] == ["primera", "la de después"], \
        "an abandoned slot has to be skipped on release, or every later delivery goes mute forever"


def test_a_crashing_speaker_releases_the_floor():
    """`finally` is the guarantee: a delivery that blows up mid-say must not hold the turn — the next one speaks."""
    calls = []

    async def _boom(text):
        calls.append(text)
        if len(calls) == 1:
            raise RuntimeError("playout exploded")

    proactive.register_speaker(_boom)

    async def _drive():
        await proactive.notify("t1", "la que explota")   # notify never raises (best-effort by contract)
        await proactive.notify("t2", "la siguiente")

    asyncio.run(_drive())
    assert calls == ["la que explota", "la siguiente"]


def test_the_quiet_check_runs_after_winning_the_turn_not_before(monkeypatch):
    """The silence that let message A start says nothing about the moment B gets the floor: if the operator is
    talking by then, B waits — and degrades on budget, instead of speaking over them."""
    monkeypatch.setattr(proactive, "PROACTIVE_MAX_WAIT", 0.2)
    busy = {"v": False}
    proactive.register_busy_probe(lambda: busy["v"])
    spk = _RecordingSpeaker(secs=0.1)
    proactive.register_speaker(spk)

    async def _drive():
        a = asyncio.create_task(proactive.notify("t1", "primera"))
        await asyncio.sleep(0.01)
        busy["v"] = True                    # the operator starts talking while A is being spoken
        b = asyncio.create_task(proactive.notify("t2", "no se habla encima"))
        await asyncio.gather(a, b)

    asyncio.run(_drive())
    assert [t for t, *_ in spk.intervals] == ["primera"]
    notes = brain_notes.drain()
    assert any("no se habla encima" in t for _, t in getattr(brain_notes, "_pending", [])) or \
           any("no se habla encima" in n for n in notes), \
        "B won the turn with the operator mid-sentence: it must degrade to a note, never talk over them"


def test_after_a_live_speech_there_is_a_breath_before_the_next():
    """`_BOT_GRACE_SECS` had been defined since INI-008 and used by NOBODY — with the queue serializing, B
    would start the very instant A's playout ends, two notices in a burst that sound like one. The breath is
    only paid coming out of live speech; an already-quiet floor speaks immediately."""
    spk = _RecordingSpeaker(secs=0.15)
    proactive.register_speaker(spk)
    speaking = {"v": False}
    proactive.register_busy_probe(lambda: speaking["v"] )

    class _BusySpeaker:
        async def __call__(self, text):
            speaking["v"] = True
            try:
                await spk(text)
            finally:
                speaking["v"] = False

    proactive.register_speaker(_BusySpeaker())

    async def _drive():
        a = asyncio.create_task(proactive.notify("t1", "primera"))
        await asyncio.sleep(0.01)
        b = asyncio.create_task(proactive.notify("t2", "segunda"))
        await asyncio.gather(a, b)

    asyncio.run(_drive())
    assert len(spk.intervals) == 2
    (_, _, end1), (_, start2, _) = spk.intervals
    assert start2 - end1 >= proactive._BOT_GRACE_SECS * 0.8, \
        f"only {start2-end1:.2f}s between the two — the breath after live speech is part of sounding like " \
        "someone explaining two things, not a machine emptying a buffer"
