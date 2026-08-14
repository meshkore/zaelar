"""bus/sse.py — SSE bridge to the frontend over the Nervous System (V2-001, T36).

`voice/observer.py` is RE-EXPRESSED over the bus: its timeline events (VAD/turns, transcripts, brain prompts/
replies, latencies, TTS, errors) are published to the **`observer`** topic, and the `GET /events` endpoint consumes
them by subscribing to that topic. The observer thus becomes **one more subscriber** to the bus, not a separate queue
system — and it also inherits `emit_sync` loop-safe delivery (the observer previously did raw cross-loop
`put_nowait` from the LiveKit job-thread).

**Strict back-compat:** the published payload IS the same `ev` dict built by `observer.emit()`, without wrapping —
`GET /events` emits exactly what it always did. This module is a thin bridge; all event-construction logic (ring,
dedup, per-session files, latencies) remains in `voice/observer.py`.
"""
import bus as _bus

TOPIC = "observer"


def publish(ev: dict):
    """Publish an observer event on the bus. Loop-agnostic (called by the LiveKit job-thread).

    This is the ONLY gate into the stream, so identity is stamped here (installation + work session):
    `observer.emit` is not the only emitter — the loop heartbeat and the `memory.updated` bridge build their dict
    manually and publish directly. Stamping is idempotent and costs a couple of cached reads."""
    try:
        from voice.observer import stamp_identity
        stamp_identity(ev)
    except Exception:
        pass
    _bus.emit_sync(TOPIC, ev)


def subscribe():
    """Subscription to the observer stream (for `GET /events`). Returns a `bus.Subscription` exposing `.get()` —
    compatible with the old `observer.subscribe()`, which returned an `asyncio.Queue`."""
    return _bus.subscribe(TOPIC)


def unsubscribe(sub):
    _bus.unsubscribe(sub)
