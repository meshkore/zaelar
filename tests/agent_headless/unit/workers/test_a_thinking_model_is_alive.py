"""A model that is THINKING is alive (V2-831 T-19 R14b).

Demo pass 5, F1 (sandbox build 86): the Bitcoin-summary worker started at +7 s and sent its first message at +236 s.
Its own transcript shows why: ONE assistant message with a 66 KB thinking block (15 700 output tokens) that took
227 s, no retry, no queue. Claude Code without `--include-partial-messages` emits nothing while the model streams,
so at +188 s the pulse said «hasn't shown a sign of life for 3 minutes» about a worker that was working.

Class: the backend's stream deltas are a sign of life. The CLI is asked for them, and the reader turns them into a
throttled `alive` event that moves the one «last signal» clock (and the stall watchdog's wait) without painting a
row or a phase. A stream that sends nothing is still silent.

Disarms: drop the flag → the command test reds; drop the `stream_event` branch → the reader and session tests red.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from nucleo.workers import stall as stall_mod
from nucleo.workers.base import WorkerSpec
from nucleo.workers.providers import claude as _c, claude_map
from nucleo.workers.providers.claude import ClaudeCodeSession
from nucleo.workers.session import SessionRecord, WorkerSession


def _delta():
    return {"type": "stream_event", "event": {"type": "content_block_delta",
                                              "delta": {"type": "thinking_delta", "thinking": "hmm"}}}


def test_the_cli_is_asked_for_its_stream_deltas(monkeypatch):
    seen: list = []

    async def _exec(*args, **kw):
        seen.extend(args)
        raise RuntimeError("captured")              # the command is all this test needs
    monkeypatch.setattr(_c, "_find_claude", lambda: "/usr/bin/true")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _exec)
    s = ClaudeCodeSession()
    try:
        asyncio.run(s.start("x", spec=WorkerSpec(task_id="9", deny_tools=True)))
    except Exception:  # noqa: BLE001
        pass
    assert seen, "the CLI was never launched"
    assert "--include-partial-messages" in seen, "without the deltas a thinking model reads as silent"


def test_deltas_become_a_throttled_alive_event_and_nothing_else():
    s = ClaudeCodeSession()
    s._task_id = "9"
    evs = [e for _ in range(200) for e in claude_map._map(s, _delta())]
    assert [e.type for e in evs] == ["alive"], f"200 deltas inside one window must give ONE liveness event: {evs}"
    s._alive_at = time.monotonic() - claude_map._ALIVE_EVERY_S - 1
    assert [e.type for e in claude_map._map(s, _delta())] == ["alive"], "the next window gives the next one"


class _Thinking:
    """A backend whose model thinks for a while (deltas only), then answers — the measured shape."""
    name, alive = "fake", True

    def __init__(self, deltas: int, every: float):
        self.deltas, self.every, self.stopped = deltas, every, False

    async def start(self, prompt, *, spec):
        pass

    async def events(self):
        s = ClaudeCodeSession()
        s._task_id = "t"
        for _ in range(self.deltas):
            await asyncio.sleep(self.every)
            s._alive_at = -1e9                        # every delta here is a new window (the throttle is tested above)
            for e in claude_map._map(s, _delta()):
                yield e
        yield type("E", (), {"type": "done", "data": {"ok": True}})()

    async def stop(self, *, grace: float = 3.0):
        self.stopped, self.alive = True, False


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_a_thinking_model_outlives_the_silence_bound(monkeypatch):
    monkeypatch.setattr(stall_mod, "_STALL_S", 0.2)
    monkeypatch.setattr(stall_mod, "_TICK_S", 0.05)
    b = _Thinking(deltas=8, every=0.1)                # 0.8 s of thinking against a 0.2 s silence bound
    rec = SessionRecord(task_id="t", goal="one-page Bitcoin summary", kind="research")
    _run(asyncio.wait_for(WorkerSession(b, type("S", (), {"model": "", "kind": "research"})(), rec).run("x"), 5))
    assert rec.status != "error" and getattr(rec, "error_class", "") != "stalled", \
        "a model that was thinking was stopped as silent"
    assert time.time() - rec.last_event_at < 1.0, "the deltas did not move the one clock"


def test_a_truly_silent_stream_is_still_stopped(monkeypatch):
    monkeypatch.setattr(stall_mod, "_STALL_S", 0.2)
    monkeypatch.setattr(stall_mod, "_TICK_S", 0.05)
    b = _Thinking(deltas=1, every=1.0)                # nothing at all for 1 s
    rec = SessionRecord(task_id="t", goal="x", kind="research")
    _run(asyncio.wait_for(WorkerSession(b, type("S", (), {"model": "", "kind": "research"})(), rec).run("x"), 5))
    assert getattr(rec, "error_class", "") == "stalled", "a stream with no deltas must still read as silent"
