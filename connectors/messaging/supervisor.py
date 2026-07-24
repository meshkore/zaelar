#
# supervisor.py — el puente WIDGET → conectores (INI-015). El widget de mensajería NO puede hacer fetch (contrato
# de aislamiento de widgets: sin red desde el cliente), así que cuando el usuario pulsa "Conectar Telegram/WhatsApp"
# el widget encola la orden por ctx.action → data.apply_action → store (pending_control). Este supervisor corre en
# el lifespan del server, drena esas órdenes cada ~1s y ejecuta el connect/disconnect real (control.py: persiste
# config en config/connectors.py + arranca/para el conector en caliente). Así todo se maneja desde la UI, sin .env.
#
# También arranca los conectores que YA estaban activados (config/connectors.json) en el primer tick — de modo que
# tras un reinicio del server, lo que el usuario dejó conectado vuelve solo.
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
                logger.debug(f"supervisor: orden desconocida {cmd!r}")
        except Exception as e:
            logger.warning(f"supervisor: orden {kind} {platform} falló: {e}")


async def _loop() -> None:
    # Arranque inicial: lo que el usuario dejó activado en la UI vuelve a levantarse tras un reinicio.
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
