"""The list lane's receipt is spoken AFTER its turn, never awaited inside it.

Measured live (2026-09-27, the demo pass after a reset): the INIT message became a list, the lane spoke «Got it
— that's several things» through `session.say` and AWAITED it. That lane runs inside the turn's generation, and
LiveKit queues a `say` behind the generation in progress, so the turn waited for its receipt and the receipt
waited for the turn. The agent sat in «thinking» from then on: every later order was generated, executed on
screen and never spoken (no assistant line on the wall either).
"""
import asyncio

from voice import proactive
from voice.engine.llm.providers import fast_lane


class _Brain:
    def __init__(self):
        self._window = []


def test_the_lane_returns_while_the_receipt_is_still_queued(monkeypatch):
    released = asyncio.Event()
    spoken = []

    async def speaker(text):
        spoken.append(text)
        await released.wait()            # the queued `say`: it cannot start until the turn ends

    async def intake(text, *, origin="voz", said=()):
        return {"ack": "Got it — that's several things."}

    monkeypatch.setattr("nucleo.batch.intake", intake)
    monkeypatch.setattr(proactive, "speaker", lambda: speaker)

    async def run():
        done = await asyncio.wait_for(
            fast_lane.task_list(_Brain(), "1. one\n2. two", lambda *a, **k: None, first_turn=False, window_max=20),
            timeout=2)
        await asyncio.sleep(0)           # let the scheduled receipt start
        released.set()
        await asyncio.sleep(0)
        return done

    loop = asyncio.new_event_loop()
    try:
        assert loop.run_until_complete(run()) is True, "the lane must end its turn with the receipt still queued"
    finally:
        loop.close()
    assert spoken == ["Got it — that's several things."], "…and the receipt is still spoken, just after"
