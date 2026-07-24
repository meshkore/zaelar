#
# service.py — el MOTOR del conector WhatsApp integrado en zaelar (INI-014; store unificado en INI-015). Corre en
# el lifespan del server (gated WA_ENABLED, siempre-on). Arranca el bridge (observe), y en bucle: lee estado+QR,
# tría los mensajes nuevos con el modelo LOCAL COMPARTIDO, y ESCRIBE el store UNIFICADO de mensajería
# (widgets/_data/mensajeria.json, platform="whatsapp") — el mismo del que también escribe Telegram. También drena
# las órdenes del operador (pending_read de su plataforma) llamando al bridge (mark-read real).
#
# Frontera: nada de esto toca ~/.hermes/hermes-agent (bridge vendorizado). El triaje NO pasa por el agente Hermes
# (privacidad + invariante ACP de voz). Ver .meshkore/docs/architecture/zaelar-hermes-federation.md.
#
import asyncio

from loguru import logger

from connectors.messaging import ingest, notify, store, triage
from connectors.whatsapp import client, config
from connectors.whatsapp.bridge_proc import bridge

PLATFORM = "whatsapp"

_task: asyncio.Task | None = None
_seen: set[str] = set()          # messageIds ya mostrados (para no resucitar lo que el operador quitó)
_published: set[str] = set()     # v2 stateless: messageIds ya publicados al bus (dedup antes de triar en el widget)
_mark_inbox = None               # v2 stateless: suscripción a msg.mark_read (creada en el loop, ver ingest.py)


def enabled() -> bool:
    # Config MANEJADA POR LA INTERFAZ: el store (escrito por la UI al pulsar "Conectar WhatsApp") manda; si no
    # dice nada, cae a WA_ENABLED (back-compat / power-user). Ver config/connectors.py.
    from config import connectors as _store
    return _store.enabled("whatsapp")


def _set_status(status: str, qr=None) -> None:
    try:
        if ingest.v2_enabled():
            ingest.publish_status(PLATFORM, status, qr)     # stateless: el widget refleja estado+QR
        else:
            store.set_platform_status(PLATFORM, status, qr)
    except Exception as e:
        logger.debug(f"WhatsApp set_status: {e}")


def _origin(m: dict) -> tuple[str, str | None]:
    if m.get("isGroup"):
        return (m.get("senderName") or "?", m.get("chatName") or "grupo")
    return (m.get("senderName") or "?", None)


async def _ingest_new() -> None:
    msgs = await client.get_messages()
    if not msgs:
        return
    if ingest.v2_enabled():
        # STATELESS: publicar los NUEVOS al bus (dedup por messageId antes de triar) — el widget mensajería
        # los tría, guarda y avisa. El conector no tría ni guarda estado.
        for m in msgs:
            mid = m.get("messageId")
            if mid and mid not in _published:
                _published.add(mid)
                ingest.publish_msg(PLATFORM, m)
        return
    verdicts = await triage.classify(msgs, config.operator_name() or None)
    surfaced = notify.surface(verdicts, _seen)
    if not surfaced:
        return
    for v in surfaced:
        _seen.add(v.get("messageId"))
        who, group = _origin(v)
        v["from"], v["group"] = who, group          # normaliza a la forma del store unificado
    store.upsert_items(PLATFORM, surfaced)
    logger.info(f"WhatsApp: +{len(surfaced)} para ti")
    await notify.announce("WhatsApp", surfaced)


async def _drain_reads() -> None:
    v2 = ingest.v2_enabled()
    keys = (_mark_inbox.drain() if _mark_inbox else []) if v2 else store.take_pending_read(PLATFORM)
    if not keys:
        return
    # El bridge espera {chatId, messageId, senderId}; la clave añade `platform` → lo quitamos antes de enviarlo.
    payload = [{"chatId": k.get("chatId"), "messageId": k.get("messageId"), "senderId": k.get("senderId")}
               for k in keys]
    try:
        await client.mark_read(payload)
    except Exception as e:
        logger.warning(f"WhatsApp mark-read falló (reintento luego): {e}")
        if v2:
            for k in keys:                       # re-publicar al bus → reintento en el siguiente tick
                ingest.publish_mark_read(k)
        else:
            store.requeue_pending_read(keys)


async def _loop() -> None:
    global _mark_inbox
    _set_status("starting", None)
    if ingest.v2_enabled() and _mark_inbox is None:
        _mark_inbox = ingest.MarkReadInbox(PLATFORM)     # suscripción en ESTE loop (server) → entrega directa
    try:
        await bridge.start()
    except Exception as e:
        logger.error(f"WhatsApp: no se pudo arrancar el bridge: {e}")
        _set_status("off", None)
        return
    connected = False
    while True:
        try:
            h = await client.health()
            st = (h or {}).get("status", "connecting")
            if st == "connected":
                if not connected:
                    logger.info("WhatsApp conectado — escuchando tu buzón")
                connected = True
                _set_status("connected", None)
                await _ingest_new()
                await _drain_reads()
            else:
                connected = False
                _set_status("connecting", (h or {}).get("qr"))
        except Exception as e:
            logger.debug(f"WhatsApp tick: {e}")
        await asyncio.sleep(config.poll_interval())


def start() -> None:
    """Arranca el motor como tarea de fondo (llamar desde el lifespan del server si WA_ENABLED=1)."""
    global _task
    if not enabled():
        _set_status("off", None)
        logger.info("WhatsApp: desactivado (WA_ENABLED!=1)")
        return
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info("WhatsApp: motor arrancado")


async def stop() -> None:
    global _task
    if _task:
        _task.cancel()
        _task = None
    await bridge.stop()
