"""The process can answer «where is this coroutine parked?» itself — `voice/debug_stacks.py`.

Born 2026-08-31: speech playout wedged BEFORE the first audio frame with no exception anywhere. The only
way to see it was a stack dump, and py-spy needs root on macOS. `/api/debug/stacks` exists so the NEXT
wedge is one curl away — but only if `collect()` really can see a task parked on ANOTHER thread's loop,
which is exactly what these tests pin.
"""
from __future__ import annotations

import asyncio
import threading
import time

from voice import debug_stacks


def test_a_parked_task_on_another_threads_loop_is_visible_with_its_await_stack():
    """The real shape of the wedge: the voice session's loop lives on a job thread, and the parked
    coroutine (a playout await) is a task of THAT loop. `collect()` called from any other thread must
    show the task and the file:line it is parked at — that file:line IS the diagnosis."""
    started = threading.Event()
    release = asyncio.Event()
    loop_holder: dict = {}

    async def _parked_like_a_wedged_playout():
        started.set()
        await release.wait()

    def _job_thread():
        loop = asyncio.new_event_loop()
        loop_holder["loop"] = loop
        loop.create_task(_parked_like_a_wedged_playout(), name="wedged-playout")
        loop.run_forever()

    t = threading.Thread(target=_job_thread, name="fake-voice-session", daemon=True)
    t.start()
    assert started.wait(timeout=5), "the parked task never started"
    loop = loop_holder["loop"]
    debug_stacks.register_loop("voice-session:test", loop)
    try:
        snap = debug_stacks.collect()
        info = snap["loops"]["voice-session:test"]
        assert info["running"] and not info["closed"]
        parked = [t_ for t_ in info["tasks"] if t_.get("name") == "wedged-playout"]
        assert parked, f"the parked task is invisible: {info['tasks']}"
        stack = "\n".join(parked[0]["stack"])
        assert "_parked_like_a_wedged_playout" in stack, \
            "the await stack must name the parked coroutine — the file:line is the whole diagnosis"
    finally:
        loop.call_soon_threadsafe(loop.stop)
        t.join(timeout=5)
        debug_stacks._loops.pop("voice-session:test", None)


def test_thread_stacks_are_always_there_and_a_closed_loop_says_so():
    """Half the value is unconditional: every OS thread's stack, even with zero registered loops. And a
    loop that died (the session ended) must be REPORTED closed, not crash the collector — the endpoint
    gets hit precisely at the messy moments."""
    dead = asyncio.new_event_loop()
    dead.close()
    debug_stacks.register_loop("voice-session:dead", dead)
    try:
        snap = debug_stacks.collect()
        assert any("MainThread" in k for k in snap["threads"]), snap["threads"].keys()
        assert snap["loops"]["voice-session:dead"]["closed"] is True
        assert snap["loops"]["voice-session:dead"]["tasks"] == []
    finally:
        debug_stacks._loops.pop("voice-session:dead", None)
