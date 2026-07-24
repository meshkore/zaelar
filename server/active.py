"""Registry of LIVE voice sessions so the agent can be force-stopped.

Each running `run_bot` registers a `shutdown` coroutine that tears the WHOLE session down (pipeline worker +
silence watchdog + Hermes agent). Two things trigger it:
  - the OFF button → POST /api/hangup → stop_all()  (deterministic; doesn't wait for WebRTC to notice the close)
  - a NEW /api/offer → stop_all() first, so only ONE bot ever runs (no orphaned workers whose silence watchdog
    keeps making the bot talk).
"""
from loguru import logger

_shutdowns: list = []   # async callables: shutdown(reason) -> None


def register(shutdown):
    _shutdowns.append(shutdown)
    return shutdown


def unregister(shutdown):
    try:
        _shutdowns.remove(shutdown)
    except ValueError:
        pass


def count() -> int:
    return len(_shutdowns)


async def stop_all(reason: str = "") -> int:
    """Shut down every live voice session. Returns how many were stopped."""
    pending, _shutdowns[:] = list(_shutdowns), []
    n = 0
    for sd in pending:
        try:
            await sd(reason)
            n += 1
        except Exception as e:
            logger.warning(f"voice session shutdown failed: {e}")
    if n:
        logger.info(f"stopped {n} live voice session(s) · {reason}")
    return n
