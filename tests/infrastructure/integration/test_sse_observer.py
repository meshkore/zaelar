#
# test_sse_observer.py — voice/observer.py re-expressed over the bus (V2-001, T36). Verifies BACK-COMPAT
# for `GET /events`: an event emitted by observer.emit() reaches an observer.subscribe() subscriber IDENTICALLY
# (which is now a bus subscription to the "observer" topic), including cross-loop delivery from the job thread.
# Run: .venv/bin/pytest tests/infrastructure/integration/test_sse_observer.py
#
import asyncio
import threading

import pytest

import bus as busmod
from voice import observer


@pytest.fixture(autouse=True)
def _clean():
    busmod.reset()
    observer.clear_log()
    yield
    busmod.reset()


def test_emit_reaches_events_subscriber_identically():
    async def run():
        sub = observer.subscribe()                     # == GET /events
        ev = observer.emit("brain", "reply", text="hola", role="assistant")
        got = await asyncio.wait_for(sub.get(), timeout=1)
        return ev, got
    ev, got = asyncio.run(run())
    # the object delivered by SSE is EXACTLY the ev constructed by observer.emit (same fields/values)
    assert got is ev
    assert got["kind"] == "brain" and got["label"] == "reply"
    assert got["text"] == "hola" and got["role"] == "assistant"
    assert {"i", "t_ms", "rel_ms", "kind", "label", "text", "role"} <= set(got.keys())


def test_observer_is_a_bus_subscriber_on_topic_observer():
    async def run():
        raw = busmod.subscribe("observer")             # raw bus subscriber to the same topic
        observer.emit("transcript", "final", text="hi")
        return await asyncio.wait_for(raw.get(), timeout=1)
    ev = asyncio.run(run())
    assert ev["kind"] == "transcript" and ev["text"] == "hi"


def test_emit_from_worker_thread_crosses_to_events_loop():
    """Voice runs in the LiveKit job thread (another loop). emit() from that thread must reach the /events
    subscriber living in the uvicorn loop—the historical put_nowait cross-loop bug, now fixed."""
    async def run():
        sub = observer.subscribe()

        def worker():                                  # thread without an asyncio loop = LiveKit job thread
            observer.emit("llm", "token", text="x")

        t = threading.Thread(target=worker)
        t.start(); t.join()
        return await asyncio.wait_for(sub.get(), timeout=1)
    ev = asyncio.run(run())
    assert ev["kind"] == "llm" and ev["label"] == "token"


def test_unsubscribe_stops_delivery():
    async def run():
        sub = observer.subscribe()
        observer.unsubscribe(sub)
        observer.emit("brain", "reply", text="y")
        await asyncio.sleep(0.01)
        return sub.queue.empty()
    assert asyncio.run(run()) is True


def test_emit_still_records_ring_and_returns_event():
    # the rest of the observer contract (in-memory ring for /api/debug) remains intact
    observer.emit("error", "boom", text="oops")
    evs = observer.debug_events(kind="error")
    assert evs and evs[-1]["label"] == "boom"
