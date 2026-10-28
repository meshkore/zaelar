# ACCOUNT LIMITS — when ZAELAR_USER_ID is set there is NO turn/TTL cap: the only thing that ends a
# session here is running OUT of Energy — a hard, uniform cutoff. Self-host never calls this
# (is_cloud_account() is False there) — same no-op-by-construction idiom as everywhere else.
#
# Closer registry: the live voice session (voice/engine/pipeline/agent.py) registers a closer gated
# on cloud_account.is_cloud_account(), invoked fire-and-forget from energy_meter.py.
#
import asyncio
import time

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


def on_balance(balance: float | None) -> None:
    """What a balance read from the ledger means here: a depleted one closes the session, a positive one ends a
    depletion notice (a top-up). Unknown (`None`) changes nothing. Never raises."""
    if should_close(balance):
        request_close("balance_depleted")
    elif balance is not None and (_exhausted.get("reason") == "balance_depleted"):
        clear_exhausted()


# --- the OUT-OF-ENERGY state, for the screen -----------------------------------------------------------------
# Closing the voice session only ever SAID it ("You're out of Energy…") and the screen showed nothing, so the
# person who heard it had no idea where to go. Every road to "out of energy" already passes `request_close`, so
# the state is recorded HERE, once, and published on the `energy` event the battery already listens to; the
# frontend paints the notice from it and from `/api/energy` after a reload. Cleared by a new lease or a top-up.
_exhausted: dict = {"reason": None, "at": 0.0}

# The reasons that mean the ACCOUNT cannot spend — the ledger or the lease endpoint SAID so. Every other reason
# (today `lease_unrenewed`: the lease could not be renewed) stopped the agent without knowing the account's state,
# and is never told as «your account is empty» nor answered with a top-up (V2-801). The frontend mirrors this set
# in `frontend/app/core/account-link.js::ACCOUNT_EMPTY`.
ACCOUNT_EMPTY = frozenset({"energy_denied", "balance_depleted"})


def says_account_empty(reason) -> bool:
    return str(reason or "") in ACCOUNT_EMPTY


def spoken_line(reason, lang=None) -> str:
    """The one line the voice says for a stop with this reason. The empty-account line ONLY for a reason that
    means it; otherwise the could-not-confirm line, and silence if a language lacks it — never the wrong claim."""
    if lang is None:
        from i18n import langs
        lang = langs.current_language()
    if says_account_empty(reason):
        return str(getattr(lang, "energy_exhausted", "") or "")
    return str(getattr(lang, "energy_unconfirmed", "") or "")
_closed_for = None        # the closer already asked to close: each session is closed ONCE, not per refused call


def close_requested() -> bool:
    """Has the live session already been asked to close (and so will say the closing line itself)?"""
    return _closer is not None and _closer is _closed_for


def exhausted() -> dict | None:
    return dict(_exhausted) if _exhausted["reason"] else None


def _publish() -> None:
    try:
        from voice.observer import emit
        emit("energy", "exhausted" if _exhausted["reason"] else "replenished",
             extra={"exhausted": _exhausted["reason"] or ""})
    except Exception as e:  # noqa: BLE001 — a lost event leaves `/api/energy` as the source; never breaks a turn
        logger.debug(f"account_limits: could not publish the energy state: {e!r}")


def note_exhausted(reason: str) -> None:
    if _exhausted["reason"] == reason:
        return
    _exhausted.update(reason=reason, at=time.time())
    _publish()


def clear_exhausted() -> None:
    global _closed_for
    _closed_for = None
    if not _exhausted["reason"]:
        return
    _exhausted.update(reason=None, at=0.0)
    _publish()


def request_close(reason: str) -> None:
    """Records the out-of-energy state, then asks the live session (if any) to close — once per session.
    Best-effort, fire-and-forget — never raises into the caller. The close is a no-op if no session registered
    a closer, and equally a no-op (logged) if called with no running event loop."""
    global _closed_for
    note_exhausted(reason)
    if _closer is None or _closer is _closed_for:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("account_limits.request_close called with no running loop — dropped")
        return
    fn = _closed_for = _closer

    async def _go() -> None:
        try:
            r = fn(reason)
            if asyncio.iscoroutine(r):
                await r
        except Exception as e:  # noqa: BLE001
            logger.warning(f"account_limits close request failed: {e}")

    asyncio.create_task(_go())
