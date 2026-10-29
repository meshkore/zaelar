"""The app's lifespan — the ONE file that says what starts, in which order, and what stops (refactor2710-13 T-03).

The start is three phases under `server/boot/` (nervous system → brain → surfaces); each returns the handles its
shutdown needs, kept on `app.state.boot`. The shutdown below is the mirror, in the order V2-038 §v3·L fixed: Brain
Workers are KILLED before the loop that supervises them comes down, so no subprocess is orphaned.

More than one listener can share this SAME app (`server/__main__.py` keeps a list of servers) — each
`uvicorn.Server` fires the ASGI lifespan independently, so this body can run more than once per process. Most pieces
are idempotent (the orchestrator loop checks `self._task is not None`), but the bus→SSE bridges had no guard: each
entry created a NEW subscription to the same topic → duplicated events in /events (2026-07-22 testing-marathon
finding, confirmed on a clean boot: "Bridge … mounted" appeared 2×). `app.state._bridges_mounted` persists between
entries because it is the SAME app, so only the FIRST entry mounts them.
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import os
import threading
from contextlib import asynccontextmanager

from loguru import logger

from server.boot import brain, nervous_system, surfaces


async def start_the_engine(app) -> dict:
    first = not getattr(app.state, "_bridges_mounted", False)
    app.state._bridges_mounted = True
    handles = await nervous_system.start(app, first)
    handles.update(await brain.start(app, first))
    await surfaces.start(app, first)
    return handles


# THE STOP IS BOUNDED. A container platform sends a stop signal and kills the process a few seconds later if it is
# still alive; an unbounded shutdown (a step waiting on a network close, a drain that never empties) turned every
# stop into a kill. Each awaitable step gets STEP_TIMEOUT_S, and the whole shutdown gets a hard deadline after which
# the process exits on its own with status 0 — the work a step could not finish in time is the work a kill would
# have lost anyway, without the clean exit.
STEP_TIMEOUT_S = float(os.getenv("ZAELAR_SHUTDOWN_STEP_S", "5"))
DEADLINE_S = float(os.getenv("ZAELAR_SHUTDOWN_DEADLINE_S", "20"))


def _arm_deadline(seconds: float) -> threading.Timer | None:
    """From here on the process WILL end within `seconds`: a daemon timer that exits it if the shutdown (or a
    non-daemon thread left behind) is still holding it. 0 disables it."""
    if seconds <= 0:
        return None

    def _exit():
        logger.warning(f"shutdown: still running after {seconds:.0f} s — exiting now")
        os._exit(0)

    t = threading.Timer(seconds, _exit)
    t.daemon = True
    t.start()
    return t


async def _stop(label: str, step) -> None:
    """One shutdown step — a zero-argument callable that imports what it needs and returns a coroutine or None. A
    failure or a timeout is said and never blocks the next step."""
    try:
        r = step()
        if inspect.isawaitable(r):
            await asyncio.wait_for(r, timeout=STEP_TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning(f"shutdown: {label} did not finish in {STEP_TIMEOUT_S:.0f} s — moving on")
    except Exception as e:  # noqa: BLE001 — a shutdown step that fails must not stop the others
        logger.debug(f"shutdown: {label} failed: {e!r}")


def _unsubscribe(sub, task) -> None:
    if task is not None:
        task.cancel()
    if sub is not None:
        import bus
        bus.unsubscribe(sub)


def _close_bus_log(log) -> None:
    log.detach()
    log.close()


def _module_stop(dotted: str, attr: str = "stop"):
    """`lambda: <module>.stop()` with the import inside, so a module that cannot be imported fails its own step."""
    def step():
        mod = importlib.import_module(dotted)
        return getattr(mod, attr)()
    return step


async def stop_the_engine(app, h: dict) -> None:
    await _stop("widget supervisor", _module_stop("widgets.supervisor"))
    await _stop("widget background", _module_stop("widgets.background"))
    await _stop("messaging supervisor", _module_stop("connectors.messaging.supervisor"))
    await _stop("homeostasis", _module_stop("nucleo.pulse.homeostasis"))
    await _stop("self watchdog", _module_stop("nucleo.pulse.self_watchdog"))
    await _stop("off-host summary", _module_stop("nucleo.pulse.offhost"))
    await _stop("whatsapp", _module_stop("connectors.whatsapp.service"))
    await _stop("telegram", _module_stop("connectors.telegram.service"))
    await _stop("email", _module_stop("connectors.email.service"))
    _lk = getattr(app.state, "lk_server", None)
    if _lk is not None:
        await _stop("livekit worker", _lk.aclose)
    # V2-038 §v3·L: ORDERLY shutdown — KILL Brain Workers (dispatch.stop → stop_all_async, killpg) BEFORE
    # bringing down the supervisor loop, so subprocesses are not orphaned when the loop dies.
    if h.get("slow_on"):
        await _stop("dispatcher", _module_stop("nucleo.dispatch"))
    if h.get("loop_on"):
        await _stop("orchestrator loop", _module_stop("nucleo.pulse.loop"))
    if h.get("susurro_on"):
        await _stop("susurro", _module_stop("nucleo.susurro"))
    await _stop("browser search", _module_stop("search.browser"))
    await _stop("meshkore", _module_stop("connectors.meshkore", "shutdown"))
    await _stop("memory→SSE bridge", lambda: _unsubscribe(h.get("mem_sse_sub"), h.get("mem_sse_task")))
    await _stop("pulse→SSE bridge", lambda: _unsubscribe(h.get("pulse_sse_sub"), h.get("pulse_sse_task")))
    if h.get("memory_on"):
        await _stop("memory", lambda: importlib.import_module("memory.api").stop(drain=True))
    if h.get("bus_log") is not None:
        await _stop("bus log", lambda: _close_bus_log(h["bus_log"]))


@asynccontextmanager
async def lifespan(app):
    handles = await start_the_engine(app)
    app.state.boot = handles
    try:
        yield
    finally:
        _arm_deadline(DEADLINE_S)
        await stop_the_engine(app, handles)
