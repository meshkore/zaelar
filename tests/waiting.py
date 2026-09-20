"""tests/waiting.py — wait for a condition against a CLOCK, and say what you were waiting for.

## Why this exists

V2-727 made a hang detectable. This makes one class of hang not happen, and the class is the one the
operator asked to have marked (2026-09-20: *«marca los tests que se cuelgan para apartarlos o arreglarlos»*).

Measured the same day, with the suites healthy, **nothing in `agent_headless`/`memory` takes over 3.5 s**.
The hangs are CONDITIONAL — they appear only when the thing being waited for stops happening:

  · `test_dispatch.py::test_listener_consumes_escalate_requested` — 1.3 s healthy, **15 minutes** when a
    leftover session in `dispatch._SESSIONS` made the dedup absorb its escalation;
  · `test_a_commission_leaves_a_durable_row.py` — 2.8 s healthy, **114 s** per case when the mechanism under
    test was disarmed.

Both were written as `for _ in range(300): await asyncio.sleep(0.05)`. That READS as fifteen seconds and is
not: the budget counts ITERATIONS, and the cost of an iteration is whatever the engine does in it — a real
recall is ~2 s — so the wall clock is unbounded exactly when something is wrong. And when the budget finally
runs out, the assertion that fails is about the RESULT («assert done is True»), which says nothing about
having waited; the cause has to be reconstructed from timestamps in the captured log.

## What this gives instead

`await until(cond, "what you expected")` — a real deadline, and a failure that NAMES the wait and how long
it lasted. A broken precondition costs seconds and arrives identified, which is the whole point of V2-727's
runner applied one level down.
"""
from __future__ import annotations

import asyncio
import time

#: Default deadline. Generous enough for a real recall with the local reranker (~2 s) plus margin, short
#: enough that a broken precondition is a pause and not a coffee break.
DEFAULT_TIMEOUT_S = 20.0
_POLL_S = 0.05


async def until(cond, what: str, *, timeout_s: float = DEFAULT_TIMEOUT_S, poll_s: float = _POLL_S):
    """Poll `cond()` until it is truthy, or fail naming `what` and the time spent.

    Returns whatever `cond()` returned, so the caller can wait for a VALUE and use it:

        row = await until(lambda: ts.task_get(uid), "the durable row to be written")

    The deadline is WALL CLOCK, never an iteration count — that distinction is the whole module.
    """
    deadline = time.monotonic() + float(timeout_s)
    while True:
        got = cond()
        if got:
            return got
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"waited {timeout_s:g}s for {what} and it never happened — the test is not slow, "
                f"something it depends on stopped working")
        await asyncio.sleep(poll_s)


def until_sync(cond, what: str, *, timeout_s: float = DEFAULT_TIMEOUT_S, poll_s: float = _POLL_S):
    """The same, for a test that is not driving an event loop."""
    deadline = time.monotonic() + float(timeout_s)
    while True:
        got = cond()
        if got:
            return got
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"waited {timeout_s:g}s for {what} and it never happened — the test is not slow, "
                f"something it depends on stopped working")
        time.sleep(poll_s)
