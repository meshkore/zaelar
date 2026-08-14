#
# supervisor.py — WIDGET -> connectors bridge (INI-015). The messaging widget CANNOT fetch (widget isolation
# contract: no client-side network), so when the user clicks "Connect Telegram/WhatsApp" the widget enqueues the
# order via ctx.action -> data.apply_action -> store (pending_control). This supervisor runs in the server lifespan,
# drains those orders every ~1s, and executes the real connect/disconnect (control.py: persists config in
# config/connectors.py + starts/stops the connector hot). This keeps everything manageable from the UI, without .env.
#
# It also starts connectors that were ALREADY enabled (config/connectors.json) on the first tick — so after a server
# restart, what the user left connected comes back by itself.
#
import asyncio

from loguru import logger

from connectors.messaging import control, store

_task: asyncio.Task | None = None
_POLL = 1.0


async def _drain_once() -> None:
    for cmd in store.take_control():
        platform = (cmd.get("platform") or "").lower()
        kind = cmd.get("cmd")
        try:
            if kind == "connect":
                await control.apply_connect(platform, cmd)
            elif kind == "disconnect":
                await control.apply_disconnect(platform, cmd)
            else:
                logger.debug(f"supervisor: unknown order {cmd!r}")
        except Exception as e:
            logger.warning(f"supervisor: order {kind} {platform} failed: {e}")


async def _loop() -> None:
    # Initial startup: what the user left enabled in the UI comes back up after a restart.
    for p in control.PLATFORMS:
        try:
            from config import connectors as cfg
            if cfg.enabled(p):
                control._services()[p].start()
        except Exception as e:
            logger.debug(f"supervisor boot {p}: {e}")
    while True:
        try:
            await _drain_once()
        except Exception as e:
            logger.debug(f"supervisor tick: {e}")
        await asyncio.sleep(_POLL)


def start() -> None:
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info("messaging supervisor arrancado (drena conexiones pedidas desde la UI)")


async def stop() -> None:
    global _task
    if _task:
        _task.cancel()
        _task = None
