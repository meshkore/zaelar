#
# ACCOUNT LIMITS (2026-08-09) — the real-account counterpart of demo_limits.py. A cloud account has
# NO turn/TTL cap by design (accountMachineConfig's docstring: "bounded by Energy balance, not a
# hard cap") — the only thing that ends a session here is running OUT of Energy. Operator's own
# words: "cuando se gasta, se acabó" — a hard, uniform cutoff (trial or a subscriber between
# renewals, same rule; see the INI-019-adjacent addenda for why this supersedes energy-model.md's
# older soft-degrade language). Self-host and demo Machines never call this (is_cloud_account() is
# False there) — same no-op-by-construction idiom as everywhere else.
#
# Mirrors demo_limits.py's closer registry EXACTLY (same shape, same asyncio.create_task/no-op-
# without-a-loop contract) so the live voice session (voice/engine/pipeline/agent.py) registers ONE
# extra closer next to the demo one, gated on cloud_account.is_cloud_account() instead of
# demo_limits.enabled().
#
import asyncio

from loguru import logger


def should_close(balance: float | None) -> bool:
    """Pure. `None` (balance unknown — e.g. the /usage report itself failed) never closes anything;
    only a confirmed depleted balance does. Never raises."""
    return balance is not None and balance <= 0


# --- closer registry — identical contract to demo_limits.py's, deliberately not shared code: the two
# modules gate on different accessors (is_cloud_account() vs demo_limits.enabled()) and a future
# change to one's semantics must never silently affect the other. ---

_closer = None  # callable(reason: str) -> None | Awaitable[None], set by the live session


def register_closer(fn) -> None:
    global _closer
    _closer = fn


def clear_closer(fn=None) -> None:
    global _closer
    if fn is None or _closer is fn:
        _closer = None


def request_close(reason: str) -> None:
    """Best-effort, fire-and-forget — never raises into the caller. No-op if no session registered a
    closer, and equally a no-op (logged) if called with no running event loop."""
    if _closer is None:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("account_limits.request_close called with no running loop — dropped")
        return
    fn = _closer

    async def _go() -> None:
        try:
            r = fn(reason)
            if asyncio.iscoroutine(r):
                await r
        except Exception as e:  # noqa: BLE001
            logger.warning(f"account_limits close request failed: {e}")

    asyncio.create_task(_go())
