"""nucleo/idle_stop.py — an engine nobody is using ends its own process, cleanly.

A deployment that runs one engine per account and pays for it by the minute relies on its platform to stop an idle
one. The platform decides "idle" from network traffic, and a half-open connection (a laptop that went to sleep with a
tab open) can look like traffic for hours. The engine knows better: it keeps a clock of REAL activity
(`observability/identity.py` — voice, workers, memory, widgets; never the pulse or a heartbeat).

So, when enabled, the pulse asks `maybe_stop()` once per tick, and the engine asks its server to exit when ALL hold:
  * no real activity for `ZAELAR_IDLE_STOP_MIN` minutes (counted from the later of that and the process start);
  * no Brain Worker session is active;
  * the next scheduled notice is not due within that same window (a deployment that wakes engines for notices
    starts it again before the next one — `nucleo/pulse/wake.py`).

The exit is the server's own graceful shutdown (`request_exit`, set by `server/__main__.py`), never a signal to
itself: the process ends with status 0, which a platform with an on-failure restart policy reads as "stopped on
purpose" and leaves stopped until the next request starts it.

Off by default: with `ZAELAR_IDLE_STOP_MIN` unset or 0 nothing here ever runs — a self-hosted engine stays up.
"""
from __future__ import annotations

import os
import time

from loguru import logger

_STARTED_MS = round(time.time() * 1000)
_state = {"requested": False}
_exit_hook = {"fn": None}


def window_min() -> int:
    try:
        return max(0, int(os.getenv("ZAELAR_IDLE_STOP_MIN", "0") or 0))
    except ValueError:
        return 0


def request_exit(fn) -> None:
    """Registered by the entrypoint: the callable that asks the server to shut down gracefully."""
    _exit_hook["fn"] = fn


def decide(now_ms: int, last_real_ms: int | None, started_ms: int, workers_active: bool,
           next_due_s: float | None, window_ms: int) -> str | None:
    """Why the engine should stop now, or None. Pure — the clock and every reading come in as arguments."""
    if window_ms <= 0:
        return None
    quiet_ms = now_ms - max(last_real_ms or 0, started_ms)
    if quiet_ms < window_ms:
        return None
    if workers_active:
        return None
    if next_due_s is not None and next_due_s * 1000 - now_ms < window_ms:
        return None
    return f"no real activity for {quiet_ms // 60000} min, no worker running, no notice due within {window_ms // 60000} min"


def _readings() -> tuple[int | None, bool, float | None]:
    from observability import identity
    last = identity.last_real_activity_ms()
    try:
        from nucleo.dispatch import registry
        workers = registry.has_active()
    except Exception:  # noqa: BLE001 — unreadable counts as busy: never stop on a guess
        workers = True
    try:
        from nucleo.pulse import scheduler
        nxt = scheduler.next_due()
    except Exception:  # noqa: BLE001
        return last, workers, 0.0                      # unreadable schedule: treat a notice as imminent
    return last, workers, (float(nxt) if nxt else None)


def maybe_stop(now: float | None = None) -> bool:
    """One pulse's check. True when it asked the server to exit (once per process)."""
    window = window_min() * 60_000
    if not window or _state["requested"] or _exit_hook["fn"] is None:
        return False
    now_ms = round((time.time() if now is None else now) * 1000)
    last, workers, nxt = _readings()
    why = decide(now_ms, last, _STARTED_MS, workers, nxt, window)
    if not why:
        return False
    _state["requested"] = True
    logger.info(f"idle stop: {why} — shutting down cleanly")
    try:
        _exit_hook["fn"]()
    except Exception as e:  # noqa: BLE001
        _state["requested"] = False
        logger.warning(f"idle stop: the exit request failed: {e!r}")
        return False
    return True


def _reset_for_tests() -> None:
    _state["requested"] = False
    _exit_hook["fn"] = None
