#
# ACCOUNT LIMITS (2026-08-09) — a cloud account has NO turn/TTL cap by design (accountMachineConfig's
# docstring: "bounded by Energy balance, not a hard cap") — the only thing that ends a session here
# is running OUT of Energy. Operator's own words: "cuando se gasta, se acabó" — a hard, uniform
# cutoff (trial or a subscriber between renewals, same rule; see the INI-019-adjacent addenda for why
# this supersedes energy-model.md's older soft-degrade language). Self-host never calls this
# (is_cloud_account() is False there) — same no-op-by-construction idiom as everywhere else.
#
# Closer registry: the live voice session (voice/engine/pipeline/agent.py) registers a closer gated
# on cloud_account.is_cloud_account(), invoked fire-and-forget from energy_meter.py.
#
import asyncio

from loguru import logger


def should_close(balance: float | None) -> bool:
    """Pure. `None` (balance unknown — e.g. the /usage report itself failed) never closes anything;
    only a confirmed depleted balance does. Never raises."""
    return balance is not None and balance <= 0


# --- closer registry ---

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
