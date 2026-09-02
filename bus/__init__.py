"""bus/ — zaelar v2 «Colmena» Nervous System (EPIC-v2-colmena, INI V2-001).

**In-process** signal pub/sub (asyncio) — the generalized form of `voice/observer.py`. **HYBRID** transport: the
voice hot path still uses direct calls (latency); the bus is for async/fan-out signals (memory updates, widgets,
escalations, loop ticks). **NO Kafka/broker** — everything lives inside this process.

Public contract:
  - `publish(topic, payload)`      — coroutine; delivers `payload` to subscribers whose pattern matches `topic`.
  - `emit_sync(topic, payload)`    — **loop-agnostic** version for threads that are NOT the main loop (e.g. the
                                     LiveKit job-thread), same pattern as `runtime.locked_ask`.
  - `subscribe(pattern="*")`       — returns a `Subscription` (async iterator + `.get()`), non-blocking.
  - `unsubscribe(sub)`             — closes a subscription (equivalent to `sub.close()`).
  - `add_sink(fn)` / `remove_sink` — SYNCHRONOUS sink called on EVERY event (`bus/log.py` uses it for the durable
                                     SQLite log; loop-agnostic, runs on the publishing thread).

**Loop-agnostic**: each `Subscription` remembers the event loop where it was created; delivery uses
`loop.call_soon_threadsafe` when the publisher runs on ANOTHER thread/loop (also fixing the cross-loop delivery the
old `observer` did with raw `put_nowait`). Sinks are invoked synchronously on the publishing thread — they must be
cheap and non-blocking (the SQLite one uses its own connection + lock).

REAL production topics (`domain.event` convention, fnmatch-style wildcard; verified by grep 2026-07-26 — fixes an
aspirational/stale list that mentioned `widget.*`/`brain.*`, which NEVER existed as topics):
`memory.updated`, `connector.msg`/`connector.status`, `loop.tick`, `escalate.requested`, `turn.completed`
(Susurro), `worker.stuck`/`worker.budget_kill`, `susurro.finding`, and `observer` — the frontend's SSE bridge, which
is NOT a per-domain topic: it carries ALL timeline events (voice, widgets, brain, cluster…) with their `kind` as a
payload field (e.g. `{"kind":"widget", ...}`), not as part of the topic name.
"""
import asyncio
import fnmatch
import threading
import time
from typing import Any, Callable

__all__ = [
    "Subscription",
    "publish",
    "emit_sync",
    "subscribe",
    "unsubscribe",
    "add_sink",
    "remove_sink",
    "reset",
]


def now_ms() -> float:
    return time.time() * 1000.0


class Subscription:
    """A live subscription to a topic pattern. It is an async iterator (`async for ev in sub`) and also exposes
    `.get()` (compat with the old `observer.subscribe()`, which returned an `asyncio.Queue`)."""

    def __init__(self, bus: "Bus", pattern: str, maxsize: int = 0):
        self._bus = bus
        self.pattern = pattern
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None  # created outside a loop (rare); resolved on first get()
        self._closed = False

    # loop-safe delivery: called by the bus from the publisher's thread/loop.
    def _deliver(self, ev: Any):
        if self._closed:
            return
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                # same loop → enqueue directly
                try:
                    self.queue.put_nowait(ev)
                except asyncio.QueueFull:
                    pass
            else:
                # other thread/loop → cross safely
                try:
                    loop.call_soon_threadsafe(self._safe_put, ev)
                except RuntimeError:
                    pass
        else:
            # no known loop: best effort
            try:
                self.queue.put_nowait(ev)
            except Exception:
                pass

    def _safe_put(self, ev: Any):
        try:
            self.queue.put_nowait(ev)
        except asyncio.QueueFull:
            pass

    async def get(self) -> Any:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return await self.queue.get()

    def __aiter__(self):
        return self

    async def __anext__(self) -> Any:
        if self._closed and self.queue.empty():
            raise StopAsyncIteration
        return await self.get()

    def close(self):
        self._closed = True
        self._bus._remove(self)

    # context-manager sugar
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class Bus:
    """The in-process bus. Normally the module singleton is used (`publish`/`subscribe`/…), but the class can be
    instantiated for isolated tests."""

    def __init__(self):
        self._subs: list[Subscription] = []
        self._sinks: list[Callable[[dict], None]] = []
        self._lock = threading.Lock()  # protects lists (touched from multiple threads)

    # ── subscription ──────────────────────────────────────────────────────────────────────────────────
    def subscribe(self, pattern: str = "*", maxsize: int = 0) -> Subscription:
        sub = Subscription(self, pattern, maxsize=maxsize)
        with self._lock:
            self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscription):
        sub.close()

    def _remove(self, sub: Subscription):
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)

    # ── sinks (log durable) ───────────────────────────────────────────────────────────────────────────
    def add_sink(self, fn: Callable[[dict], None]):
        with self._lock:
            if fn not in self._sinks:
                self._sinks.append(fn)

    def remove_sink(self, fn: Callable[[dict], None]):
        with self._lock:
            if fn in self._sinks:
                self._sinks.remove(fn)

    # ── publication ───────────────────────────────────────────────────────────────────────────────────
    def _dispatch(self, topic: str, payload: Any):
        """Synchronous dispatch (does not block, only enqueues / calls sinks). Shared by publish + emit_sync."""
        with self._lock:
            subs = list(self._subs)
            sinks = list(self._sinks)
        for sub in subs:
            if _match(sub.pattern, topic):
                sub._deliver(payload)
        # sinks: durable log + any synchronous consumer. The sink event DOES carry metadata.
        if sinks:
            rec = {"topic": topic, "ts_ms": now_ms(), "payload": payload}
            for fn in sinks:
                try:
                    fn(rec)
                except Exception:
                    pass

    async def publish(self, topic: str, payload: Any = None):
        """Publish an event. Async by contract, but dispatch is non-blocking (only enqueues)."""
        self._dispatch(topic, payload)

    def emit_sync(self, topic: str, payload: Any = None):
        """Publish from ANY thread/loop (LiveKit job-thread, subprocess callbacks…). Loop-agnostic: each subscriber
        receives delivery on ITS loop through call_soon_threadsafe."""
        self._dispatch(topic, payload)

    def reset(self):
        """Clear subscribers and sinks (for tests)."""
        with self._lock:
            for s in self._subs:
                s._closed = True
            self._subs.clear()
            self._sinks.clear()


def _match(pattern: str, topic: str) -> bool:
    if pattern == "*" or pattern == topic:
        return True
    return fnmatch.fnmatchcase(topic, pattern)


# ── module singleton ────────────────────────────────────────────────────────────────────────────────────
_BUS = Bus()


async def publish(topic: str, payload: Any = None):
    await _BUS.publish(topic, payload)


def emit_sync(topic: str, payload: Any = None):
    _BUS.emit_sync(topic, payload)


def subscribe(pattern: str = "*", maxsize: int = 0) -> Subscription:
    return _BUS.subscribe(pattern, maxsize=maxsize)


def unsubscribe(sub: Subscription):
    _BUS.unsubscribe(sub)


def add_sink(fn: Callable[[dict], None]):
    _BUS.add_sink(fn)


def remove_sink(fn: Callable[[dict], None]):
    _BUS.remove_sink(fn)


def reset():
    _BUS.reset()


def get_bus() -> Bus:
    return _BUS
