#
# reseed.py — tell every LIVE messaging connector to forget its own delivery memory (2026-09-08).
#
# Reset (`widgets/reset.py` -> `widgets/mensajeria/data.py::blank()`) wipes the widget's `items` AND its durable
# `taken` ledger (V2-607), but it is a WIDGET-side operation — it never touches a connector's own process state.
# A connector like email keeps a private in-memory record of what it already handed over (`_seen`/`_published` in
# `connectors/email/service.py`), populated once at connect and on every real delivery, and otherwise cleared ONLY
# by a full `stop()`. So a message the connector already delivered once stays "already delivered" forever from its
# own point of view, even after Reset erases every trace of it from the widget — genuinely unread mail vanishes
# from view until the engine restarts. Measured live: 1081 real unread in Gmail, zero reaching the widget after a
# Reset, `taken` holding no `email:*` entry at all.
#
# Called from `nucleo/reset.py::reset_all()`, fire-and-forget, ONLY when mensajería was actually blanked. Each
# connector's own `reseed()` decides how much to release (email: the same BACKFILL-sized recent-unread slice a
# fresh connect already produces) — this module just calls whichever connectors are actually live, best-effort.
#
from loguru import logger


async def reseed_all() -> dict:
    """Best-effort, one entry per connector that is actually enabled. A connector with no `reseed()` (or not
    live) is silently skipped — never a reason for Reset itself to fail or slow down."""
    out: dict = {}
    try:
        from connectors.email import service as email_service
        if email_service.enabled():
            out["email"] = await email_service.reseed()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"messaging reseed: email falló: {e}")
    return out
