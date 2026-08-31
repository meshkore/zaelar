"""widgets/background.py: BACKGROUND EXECUTION for widgets with a CYCLE (V2-034).

A widget does not always work only while it is visible. Some must stay alive even when their card is closed: a
messaging widget receives connector messages, triages them, and writes new information to memory, so if the
operator asks by voice whether there are messages, zaelar answers with current data even if the widget was never
opened. This is a first-class widget-system capability: background execution with a declared cycle
(every 1s / 1m / 1h...).

## Two ways to run in the background (one declarative idea)

A widget declares its cycle in `manifest.json`:

    "background": { "every": "1m" }          # object, or shortcut string "background": "1m", or seconds: 60

  - **passive + `background`**: the lightweight path (new in V2-034). There is no owned process; this scheduler
    calls `data.py:tick()` every `every`, outside the voice hot path (`asyncio.to_thread`, because `data.py` is
    synchronous stdlib code). `tick()` refreshes data (`store.save()` only when it changes -> SSE refresh for the
    open card, no flood because save is idempotent) and writes relevant information to memory
    (`memory.ingest_message`/`memory.write` with `slot` for supersede). Best for pollers/refreshers/dumps that do
    NOT need a live connection.
  - **backed**: the heavier path (already existing, `widgets/supervisor.py`). An `owner.py` has its own process
    and live connection (browser Chromium, messaging connectors). A backed widget is background by nature: its
    owner self-schedules. If it also declares `background`, this scheduler enqueues a `"tick"` command in its
    mailbox every `every`; the owner handles it if it wants to. If it does not declare it, it is not bothered.

## Invariants

  - **Outside the hot path.** Runs in the server loop (lifespan, the same loop as voice and the backed
    supervisor), but passive `tick()` calls go to a thread (`to_thread`), so they never block the event loop or
    the voice turn.
  - **Total isolation.** A `tick()` that crashes or runs long does NOT bring down voice, another widget, or the
    scheduler: it is caught, traced (`observer`, kind `background`), and the scheduler continues. Per-widget
    overlap is avoided; if the previous tick is still running, that cycle is skipped.
  - **Minimum period = 1s.** `every` is normalized to seconds (>=1).
"""
from __future__ import annotations

import asyncio
import importlib
import re
import time

from loguru import logger

from . import runtime

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_tasks: dict[str, asyncio.Task] = {}       # wid -> supervised periodic task
_inflight: set[str] = set()                # wids whose tick is still running (prevents overlap)


def parse_period(v) -> int | None:
    """Normalize a cycle spec to seconds (minimum 1). Accepts int/float seconds, a dict `{"every": ...}`, or a
    string `"90"`, `"30s"`, `"5m"`, `"1h"`, `"1d"`. Returns None when invalid."""
    if isinstance(v, dict):
        v = v.get("every")
    if isinstance(v, bool):                # bool is a subtype of int; reject it explicitly
        return None
    if isinstance(v, (int, float)):
        return max(1, int(v))
    if isinstance(v, str):
        m = re.fullmatch(r"\s*(\d+)\s*([smhd]?)\s*", v.lower())
        if m:
            return max(1, int(m.group(1)) * _UNITS.get(m.group(2) or "s", 1))
    return None


def background_period(w: dict) -> int | None:
    """The cycle in seconds declared by a widget manifest, or None if it does not run in the background."""
    return parse_period(w.get("background")) if w.get("background") is not None else None


def _emit(label: str, wid: str, text: str = "") -> None:
    try:
        from voice.observer import emit
        emit("background", label, text=(f"{wid}: {text}" if text else wid), extra={"id": wid})
    except Exception:
        pass


class TickCtx:
    """Context passed by the scheduler to `tick(ctx)`: the sanctioned layer for a passive widget to write to
    memory without importing the core from its data.py (stdlib-only by design; the generator gate enforces it).
    Mirrors the `ctx` in `widget.js`. Everything is best-effort: a write failure does not break the tick."""

    def __init__(self, wid: str):
        self.widget_id = wid

    def remember(self, text: str, *, slot: str | None = None, kind: str = "note",
                 importance: float = 0.4, level: str = "mid", **extra) -> None:
        """Write data to central memory. `slot` gives supersede: the latest value wins instead of accumulating.

        The slot is ALWAYS namespaced with this widget's id (V2-242). Memory's readers separate «the operator's
        own facts» from «pills written by a background job» BY THE SHAPE OF THE KEY — dots for the person
        (`operator.location`), a namespace for background (`<widget>:<key>`); the passive block has excluded the
        namespaced ones since the 2026-07-14 audit, and the worker dossier since `memory_agent` (2026-08-21). That
        convention was a PROMISE with no lock: nothing stopped a tick from writing `operator.location` and minting
        a fact about the person, and nothing stopped an unslotted note from landing under the header «WHAT YOU KNOW
        ABOUT THE OPERATOR». Here the lock is put on the write side, which is the only place that KNOWS a background job
        is the author.

        It is not a blanket ban: a namespaced pill still reaches the reader when the task names it («the weather in
        Soria»), which is the promise the 2026-07-14 note made and this keeps.
        """
        try:
            from memory import api as memory
            meta = {"widget": self.widget_id, **(extra.pop("meta", None) or {})}
            memory.write(text, kind=kind, level=level, importance=importance, slot=self._own_slot(slot),
                         meta=meta, **extra)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"background[{self.widget_id}] ctx.remember failed: {e}")

    def _own_slot(self, slot) -> str:
        """`<widget-id>:<whatever was requested>`. Without a slot, `<widget-id>:note` — because nobody filters a
        note WITHOUT a slot either: the convention is read from the key, so a pill without a key enters the
        operator's dossier as if it were theirs, and on top of that accumulates without replacing the previous one."""
        raw = " ".join(str(slot or "").split()).strip()
        base = str(self.widget_id or "widget").strip()
        if not raw:
            return f"{base}:note"
        return raw if raw.startswith(f"{base}:") else f"{base}:{raw}"

    def ingest(self, source: str, entity: str, text: str, **kw):
        """Write incoming data from a source (messaging/feed...) through the typed memory path."""
        try:
            from memory import api as memory
            return memory.ingest_message(source, entity, text, **kw)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"background[{self.widget_id}] ctx.ingest failed: {e}")
            return None

    def save(self, data: dict):
        """Persist the widget store; idempotent, so SSE emits only when it changed."""
        from . import store
        return store.save(self.widget_id, data)


def _call_tick(wid: str):
    """Call the widget's `data.py:tick(ctx)` (synchronous stdlib). Runs in a thread (`to_thread`). Accepts both
    `tick(ctx)` with memory access and `tick()` with no arguments for compatibility."""
    import inspect
    mod = importlib.import_module(f"widgets.{wid}.data")
    fn = getattr(mod, "tick", None)
    if not callable(fn):
        return None
    try:
        takes_arg = len(inspect.signature(fn).parameters) >= 1
    except (TypeError, ValueError):
        takes_arg = False
    return fn(TickCtx(wid)) if takes_arg else fn()


async def _tick_once(wid: str, kind: str) -> None:
    # V2-092: when the agent is stopped, cycles do not run. A "stopped agent" that keeps polling connectors and
    # writing to memory is not really stopped. The loop is NOT cancelled; it stays awake counting, so starting
    # again resumes ticks without rebuilding the scheduler.
    try:
        from nucleo import runstate
        if runstate.stopped():
            return
    except Exception:
        pass
    if wid in _inflight:                    # previous cycle is still running -> skip this one; do not queue slow work
        _emit("skip", wid, "previous tick in progress")
        return
    _inflight.add(wid)
    try:
        if kind == "backed":
            from . import supervisor
            supervisor.enqueue(wid, "tick", {})     # owner decides whether to handle it
            _emit("tick", wid, "-> owner")
        else:
            t0 = time.time()
            await asyncio.to_thread(_call_tick, wid)
            _emit("tick", wid, f"{round((time.time() - t0) * 1000)}ms")
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        _emit("error", wid, str(e))
        logger.warning(f"background[{wid}] tick failed (isolated): {e}")
    finally:
        _inflight.discard(wid)


async def _run_widget(wid: str, period: int, kind: str) -> None:
    """Periodic loop for one widget. Waits a little at startup to stagger ticks, then runs every `period`s."""
    await asyncio.sleep(min(period, 2.0))
    while True:
        try:
            await _tick_once(wid, kind)
        except asyncio.CancelledError:
            break
        await asyncio.sleep(period)


def start() -> None:
    """Start, during server lifespan, the background scheduler for every widget declaring `background`.
    Idempotent. A passive widget with `background` MUST have `tick()` in data.py; otherwise it is skipped with a
    warning and never breaks startup."""
    for w in runtime.catalog():
        period = background_period(w)
        if not period:
            continue
        wid = w.get("id") or ""
        if not wid or wid in _tasks:
            continue
        kind = "backed" if (w.get("kind") or "passive") == "backed" else "passive"
        if kind == "passive":
            try:
                mod = importlib.import_module(f"widgets.{wid}.data")
                if not callable(getattr(mod, "tick", None)):
                    logger.warning(f"background[{wid}] declares 'background' but data.py has no tick(); skipped")
                    _emit("no_tick", wid)
                    continue
            except Exception as e:  # noqa: BLE001
                logger.warning(f"background[{wid}] could not import data.py: {e}")
                continue
        _tasks[wid] = asyncio.create_task(_run_widget(wid, period, kind))
        logger.info(f"background[{wid}] every {period}s ({kind})")
        _emit("start", wid, f"every {period}s ({kind})")


async def stop() -> None:
    """Cancel all periodic loops (lifespan finally)."""
    for wid, task in list(_tasks.items()):
        task.cancel()
    _tasks.clear()
    _inflight.clear()


def scheduled() -> list[str]:
    """Ids of widgets with a live background loop, for observability/tests."""
    return [wid for wid, t in _tasks.items() if not t.done()]
