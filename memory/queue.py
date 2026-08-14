"""memory/queue.py — async memory write queue (V2-002 · T45).

ALL writes enter here. A **single consumer** drains the queue and calls the writer (`memory/writer.py`) -> zero write
collisions; readers (retriever/state) go direct in WAL without blocking. Insertion is NOT urgent: it may take time
(computes local embeddings), but never blocks the hot path.

**Loop-agnostic** (same pattern as `bus/` and `runtime.locked_ask`): writers may live in another thread/loop
(LiveKit job-thread, subprocess callbacks). `submit()` queues safely from any thread — if it is the consumer loop,
`put_nowait`; otherwise, `call_soon_threadsafe`. If no consumer has started yet (e.g. tests/standalone), `submit()`
applies the write **inline** (best-effort) to avoid losing it.

Each item = `(op, args, kwargs, future|None)`. `op` maps to `writer.OPS`. If a `future` is passed, it is resolved
with the result (used by `api.write` when the caller wants the id back).
"""
import asyncio
import threading
from typing import Any

from loguru import logger

from . import writer as _writer


class MemoryQueue:
    def __init__(self):
        self._q: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._lock = threading.Lock()
        self._running = False

    # ── lifecycle ──────────────────────────────────────────────────────────────────────────────────────
    async def start(self):
        """Start the consumer in the current loop. Idempotent."""
        with self._lock:
            if self._running:
                return
            self._loop = asyncio.get_running_loop()
            self._q = asyncio.Queue()
            self._running = True
            self._task = self._loop.create_task(self._consume())

    async def stop(self, drain: bool = True):
        """Stop the consumer. If `drain`, process pending items before exiting."""
        if not self._running:
            return
        if drain and self._q is not None:
            await self._q.join()
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None

    async def join(self):
        """Wait until the queue is empty (tests: submit -> join -> query)."""
        if self._q is not None:
            await self._q.join()

    # ── single consumer ────────────────────────────────────────────────────────────────────────────────
    async def _consume(self):
        assert self._q is not None
        while True:
            op, args, kwargs, fut = await self._q.get()
            try:
                result = self._apply(op, args, kwargs)
                if fut is not None and not fut.done():
                    fut.get_loop().call_soon_threadsafe(fut.set_result, result)
                # Live observability (V2-014): re-emit `memory.updated` with the REAL id once the async write
                # finished (`api.write` emits before insert and has no id yet). This lets the memory viewer TINT the
                # exact node (green=high, amber=overwrite).
                self._emit_written(op, args, result)
            except Exception as e:  # a bad write NEVER takes down the consumer
                if fut is not None and not fut.done():
                    fut.get_loop().call_soon_threadsafe(fut.set_exception, e)
                else:
                    # WITHOUT future (normal case: api.write() fire-and-forget), the error used to disappear
                    # silently — join() returned as if the write had succeeded while the data was truly lost
                    # (2026-07-26 audit finding). Log it ALWAYS even if nobody waits for the result — still does not
                    # take down the consumer, but is no longer invisible.
                    logger.error(f"memory queue: escritura '{op}' falló y se descarta (fire-and-forget): {e}")
            finally:
                self._q.task_done()

    @staticmethod
    def _emit_written(op: str, args: tuple, result: Any) -> None:
        """Fine-grained post-write signal with affected id (best-effort, never breaks the consumer)."""
        try:
            if op == "write" and result is not None:
                payload = {"op": "write", "id": int(result)}
            elif op == "supersede" and args:
                payload = {"op": "supersede", "id": int(args[0])}
            else:
                return
            import bus
            bus.emit_sync("memory.updated", payload)
        except Exception:
            pass

    @staticmethod
    def _apply(op: str, args: tuple, kwargs: dict) -> Any:
        fn = _writer.OPS.get(op)
        if fn is None:
            raise ValueError(f"unknown memory op: {op!r}")
        return fn(*args, **kwargs)

    # ── enqueue (from any thread) ──────────────────────────────────────────────────────────────────────
    def submit(self, op: str, *args, future: asyncio.Future | None = None, **kwargs):
        """Enqueue a write. Loop-agnostic. If there is no consumer, apply inline (best-effort)."""
        item = (op, args, kwargs, future)
        if not self._running or self._q is None or self._loop is None:
            # no consumer: apply inline so the write is not lost (standalone/tests).
            try:
                res = self._apply(op, args, kwargs)
                if future is not None and not future.done():
                    future.get_loop().call_soon_threadsafe(future.set_result, res)
            except Exception as e:
                if future is not None and not future.done():
                    future.get_loop().call_soon_threadsafe(future.set_exception, e)
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            self._q.put_nowait(item)
        else:
            self._loop.call_soon_threadsafe(self._q.put_nowait, item)


# module singleton
_QUEUE = MemoryQueue()


def get_queue() -> MemoryQueue:
    return _QUEUE
