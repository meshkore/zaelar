#
# DEMO LIMITS (INI-018 T6) — turn/TTL caps for the cloud demo, off by default everywhere else.
#
# These are OPS-only deployment knobs (set by the cloud demo's Fly Machine env — see
# cloud/infra/demo-session-worker/), never surfaced in the ⚙ UI like config/settings.py's knobs:
# self-host and the operator's own cloud account never set them, so `enabled()` is False and every
# check below is a no-op. Read live (like voice/attention.py's mode()/window_s()) rather than frozen
# at boot, matching the rest of the ops-env-var idiom in this codebase.
#
# The CLOSER is a process-level registry (same shape as voice/proactive.py's speaker registry): the
# live voice session (voice/engine/pipeline/agent.py) registers how to actually end itself, and this
# module — which has no access to `ctx`/`session` — just requests it.
#
import asyncio
import os
import time

from loguru import logger


def max_turns() -> int | None:
    v = (os.getenv("ZAELAR_DEMO_MAX_TURNS") or "").strip()
    if not v:
        return None
    try:
        n = int(v)
    except ValueError:
        return None
    return n if n > 0 else None


def ttl_secs() -> float | None:
    v = (os.getenv("ZAELAR_DEMO_TTL_SECS") or "").strip()
    if not v:
        return None
    try:
        n = float(v)
    except ValueError:
        return None
    return n if n > 0 else None


def enabled() -> bool:
    return max_turns() is not None or ttl_secs() is not None


def check(turn_count: int, started_at: float, *, now: float | None = None) -> str | None:
    """Pure. Returns 'max_turns' | 'ttl' | None — never raises, never touches env beyond the two
    getters above. `turn_count` is turns COMPLETED so far (0-based); the cap fires once the count
    reaches the limit, not after exceeding it (so ZAELAR_DEMO_MAX_TURNS=1 ends after the 1st turn)."""
    mt = max_turns()
    if mt is not None and turn_count >= mt:
        return "max_turns"
    tt = ttl_secs()
    if tt is not None:
        elapsed = (now if now is not None else time.time()) - started_at
        if elapsed >= tt:
            return "ttl"
    return None


# --- closer registry — mirrors voice/proactive.py's _speaker/_busy_probe pattern ---

_closer = None  # callable(reason: str) -> None | Awaitable[None], set by the live session


def register_closer(fn) -> None:
    global _closer
    _closer = fn


def clear_closer(fn=None) -> None:
    global _closer
    if fn is None or _closer is fn:
        _closer = None


def request_close(reason: str) -> None:
    """Best-effort, fire-and-forget — never raises into the caller's turn. No-op if no session
    registered a closer (e.g. this got enabled outside a real voice session, or double-fired), and
    equally a no-op (logged) if called with no running event loop (e.g. a unit test) — production
    call sites are always inside the live turn's coroutine, so a loop is always running there."""
    if _closer is None:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("demo_limits.request_close called with no running loop — dropped")
        return
    fn = _closer

    async def _go() -> None:
        try:
            r = fn(reason)
            if asyncio.iscoroutine(r):
                await r
        except Exception as e:  # noqa: BLE001
            logger.warning(f"demo_limits close request failed: {e}")

    asyncio.create_task(_go())
