"""Live-process stack introspection — `GET /api/debug/stacks` (loopback debug surface).

Born 2026-08-31, during the third voice outage of the day: speech playout wedged BEFORE the first audio
frame with no exception anywhere — TTS synthesized the full reply, the state machine never reached
`speaking`, and nothing in any log said where the coroutine was parked. `py-spy` needs root on macOS, so
the process has to be able to answer the question itself.

Two views, because an asyncio wedge is invisible in thread stacks alone:
  - every OS thread's current stack (`sys._current_frames()` — the loop thread just shows the selector);
  - every asyncio task of every REGISTERED loop, with its await stack. The voice session runs on its own
    job-thread loop, which nothing global knows about — `voice/engine/pipeline/agent.py` registers it here
    at session start.

Reading a loop's task set from another thread is not part of asyncio's contract; it is a read-only
best-effort walk, acceptable for a debug endpoint and worthless for anything else. Do not build product
behavior on this module.
"""
from __future__ import annotations

import asyncio
import sys
import threading
import traceback

_loops: dict[str, asyncio.AbstractEventLoop] = {}


def register_loop(name: str, loop: asyncio.AbstractEventLoop) -> None:
    """Make `loop`'s tasks visible to `collect()`. Re-registering a name replaces it (a new voice session
    replaces the previous session's loop — dead loops are reported as such, never removed silently)."""
    _loops[name] = loop


def _thread_stacks() -> dict[str, list[str]]:
    names = {t.ident: t.name for t in threading.enumerate()}
    out: dict[str, list[str]] = {}
    for ident, frame in sys._current_frames().items():
        out[f"{names.get(ident, '?')}·{ident}"] = traceback.format_stack(frame)
    return out


def _task_stacks(loop: asyncio.AbstractEventLoop) -> list[dict]:
    out: list[dict] = []
    try:
        tasks = asyncio.all_tasks(loop)
    except Exception as e:  # noqa: BLE001
        return [{"error": f"all_tasks failed: {e}"}]
    for t in tasks:
        try:
            frames = t.get_stack(limit=12)
            stack = []
            for f in frames:
                code = f.f_code
                stack.append(f"{code.co_filename}:{f.f_lineno} {code.co_name}")
            out.append({
                "name": t.get_name(),
                "coro": repr(t.get_coro())[:300],
                "done": t.done(),
                "stack": stack,
            })
        except Exception as e:  # noqa: BLE001
            out.append({"error": f"task introspection failed: {e}"})
    return out


def collect() -> dict:
    loops = {}
    for name, loop in list(_loops.items()):
        loops[name] = {
            "closed": loop.is_closed(),
            "running": loop.is_running(),
            "tasks": _task_stacks(loop) if not loop.is_closed() else [],
        }
    return {"threads": _thread_stacks(), "loops": loops}
