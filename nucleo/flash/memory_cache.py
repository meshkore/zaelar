"""nucleo/flash/memory_cache.py — FlashBrain MEMORY block cached OUTSIDE the turn (V2-011 · T114).

The problem (V2-004 → V2-011): the port to `nucleo/` put the COMPLETE memory retriever in the turn's hot path
— `build_flash_system(recall_query=text)` triggered `memory.query()` (HTTP embeddings to Ollama + RRF + graph +
reinforcement) SYNCHRONOUSLY in the event loop before the LLM, on every turn. The T113 baseline confirms it: 112–452
ms per turn, blocking the loop.

V1 (`brains/duo/briefing.py`) NEVER queried memory per turn: it requested a briefing ONCE at startup and CACHED it
(TTL 300 s), injecting the string into the prompt. This module is the v2 equivalent without Hermes: the block
comes from the PROPER central memory — from the **fixed state table** (`memory.state()`, name/address/location/
topics/recent items: the "startup memory" that neutralizes "who are you?") — and is cached per process with a
short TTL + **async refresh** + **invalidation through the bus's `memory.updated` signal**. The turn reads the
cached string instantly; it NEVER triggers the retriever in the event loop.

The specific semantic recall (`memory.query`) does NOT live here — it is on demand and outside the loop (T115/T116).
"""
from __future__ import annotations

import asyncio
import os
import threading
import time

from loguru import logger

_TTL = float(os.getenv("NUCLEO_MEM_CACHE_TTL", "300"))   # s; short → near-live recall, but outside the turn
_lock = threading.Lock()
_cache = {"block": "", "op": "", "at": 0.0, "dirty": True}
_refreshing = threading.Event()   # dedup: only one refresh in flight at a time
_bus_wired = {"v": False}
# Stats from the last composition (memory observability, V2-014 Task 2): the turn reads them to render
# MEMORY rows (state/short) in the log column, showing what was read and its size.
_last_stats: dict = {"has_state": False, "state_fields": 0, "short_count": 0, "short_chars": 0,
                     "salient_count": 0, "has_mission": False, "op": ""}


def _set_stats(**kw) -> None:
    with _lock:
        _last_stats.update(kw)


def stats() -> dict:
    """Stats from the last composed memory read (for the observability column)."""
    with _lock:
        return dict(_last_stats)


# ── block composition (delegates to memory.compose_state; ALWAYS outside the loop) ─────────────────────────
def _mission_fallback() -> str:
    """Default MISSION text from the language catalog (single language source). Passed to
    `compose_state` to avoid reversing the memory→voice dependency, and SEEDED into state in `prime()`."""
    try:
        from voice.engine.core import langs
        return langs.current_language().mission or ""
    except Exception:
        return ""


def _compose() -> tuple[str, str]:
    """Composes the SHARED STATE block by delegating to `memory.compose_state()` (V2-027 — memory owns the
    A+B+C composition; this module only CACHES it off the hot path). Returns (block, operator_name).
    Best-effort: ('', '') if memory is unavailable. ALWAYS runs in a thread — never in the event loop."""
    try:
        from memory import api as memory
        block, op, stats = memory.compose_state(mission_fallback=_mission_fallback())
    except Exception:
        return "", ""
    _set_stats(**stats)
    return block, op


# ── public API ─────────────────────────────────────────────────────────────────────────────────────────
def get() -> tuple[str, str]:
    """Reads the cached block (block, operator_name) INSTANTLY — never blocks the turn. If dirty or
    expired, schedules an async refresh (fire-and-forget) and returns the current value (possibly stale, but
    kept fresh by the short TTL + invalidation through `memory.updated`)."""
    _wire_bus()
    with _lock:
        block, op, at, dirty = _cache["block"], _cache["op"], _cache["at"], _cache["dirty"]
    if dirty or (time.time() - at) > _TTL:
        if _schedule_refresh():          # SYNCHRONOUS refresh (no loop) → re-read the now-fresh value
            with _lock:
                block, op = _cache["block"], _cache["op"]
    return block, op


def _seed_mission() -> None:
    """SEEDS the MISSION into memory (state.mission) at startup if it is not there yet, taking it from the language
    catalog (`langs`, the operator's language). This way zaelar's identity LIVES in memory — visible and editable on
    the map — instead of in a hardcoded English prompt (V2-027). Idempotent: if a mission already exists, does not
    overwrite it (preserves an evolved mission). Best-effort; runs in the `prime` thread (startup), never in the turn."""
    try:
        from memory import api as memory
        cur = (memory.state().get("mission") or "").strip()
        if cur:
            return
        text = _mission_fallback()
        if text:
            memory.set_state({"mission": text})   # emits memory.updated → prime's refresh recomposes after this
    except Exception:
        pass


async def prime() -> None:
    """Seeds the MISSION (if missing) and composes the block ONCE at session startup (analogous to the v1 briefing),
    so the FIRST turn already has identity + startup memory (name greeting). Runs in a thread; never
    disrupts voice startup."""
    _wire_bus()
    await asyncio.to_thread(_seed_mission)
    await _do_refresh()


async def refresh() -> None:
    """Force a fresh state composition from an off-hot-path caller.

    Memory ingestion and explicit session barriers use this after their writes have completed. This preserves
    the instant `get()` contract while ensuring the *next* turn cannot observe a superseded identity value.
    """
    await _do_refresh()


def invalidate() -> None:
    """Marks the block as dirty → the next `get()` schedules a refresh. Called by the `memory.updated` sink."""
    with _lock:
        _cache["dirty"] = True


def reset() -> None:
    """Clears state (tests): cache, in-flight refresh, and bus subscription."""
    with _lock:
        _cache.update({"block": "", "op": "", "at": 0.0, "dirty": True})
    _refreshing.clear()
    if _bus_wired["v"]:
        try:
            import bus
            bus.remove_sink(_on_bus)
        except Exception:
            pass
        _bus_wired["v"] = False


# ── internal mechanics ────────────────────────────────────────────────────────────────────────────────────
def _schedule_refresh() -> bool:
    """Schedules `_do_refresh()` on the current loop (fire-and-forget). If there is no loop (tests/standalone), refreshes
    inline synchronously — never leaves the block empty because no loop exists. Returns True ONLY if it refreshed
    synchronously (so `get()` re-reads the now-fresh value)."""
    if _refreshing.is_set():
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        _refreshing.set()
        task = loop.create_task(_do_refresh())
        task.add_done_callback(lambda t: (_refreshing.clear(), t.cancelled() or t.exception()))
        return False
    # no loop: synchronous refresh (compose is cheap: only memory.state()).
    block, op = _compose()
    _store(block, op)
    return True


async def _do_refresh() -> None:
    """Recomposes the block in a thread and updates the cache. Best-effort."""
    try:
        block, op = await asyncio.to_thread(_compose)
        _store(block, op)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"nucleo memory-cache refresh skipped: {e}")


def _store(block: str, op: str) -> None:
    with _lock:
        # SACRED IDENTITY FLOOR (fix for "doesn't know my name although it is in state"): `compose_state` may
        # FAIL transiently (DB read under contention in sessions with many writes) and return
        # ('',''). We NEVER overwrite a GOOD block with empty → name/address/mission never disappear mid-session
        # because of a transient failure. Legitimate emptiness (fresh install / `reset()`) starts with an already
        # empty cache, so this guard does not block it; it only protects against accidental deletion of live state.
        if not (block or "").strip() and (_cache["block"] or "").strip():
            _cache["dirty"] = True     # keep the good one, but retry the refresh on the next get()
            return
        _cache["block"] = block
        _cache["op"] = op
        _cache["at"] = time.time()
        _cache["dirty"] = False


def _wire_bus() -> None:
    """Subscribes invalidation to `memory.updated` with a bus SINK (synchronous, loop-agnostic — like the
    durable log). Cheap: filters the topic and marks it dirty. Idempotent."""
    if _bus_wired["v"]:
        return
    try:
        import bus
        bus.add_sink(_on_bus)
        _bus_wired["v"] = True
    except Exception:
        pass


def _on_bus(rec: dict) -> None:
    if rec.get("topic") == "memory.updated":
        invalidate()
