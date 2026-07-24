#
# service.py — el MOTOR del conector Telegram integrado en zaelar (INI-015). Corre EN PROCESO en el lifespan del
# server (gated TG_ENABLED, siempre-on), como una tarea asyncio — Telethon es un cliente asyncio puro, NO hay
# subproceso Node ni bridge que vendorizar (a diferencia de WhatsApp). Telegram es "black-box lib": una librería
# de terceros (Telethon), sin ninguna dependencia de Hermes.
#
# Flujo: login por QR (client.qr_login(), QR pintado EN EL WIDGET vía segno) → escucha events.NewMessage →
# clasifica con el modelo LOCAL COMPARTIDO (connectors/messaging/triage) → escribe el store UNIFICADO
# (widgets/_data/mensajeria.json, platform="telegram") → drena pending_read marcando leído (send_read_acknowledge).
# El clasificador NO pasa por el agente Hermes (privacidad + invariante ACP de voz). Read-only + mark-read.
#
import asyncio
import base64
import io

from loguru import logger

from connectors.messaging import ingest, notify, store, triage
from connectors.telegram import config

_task: asyncio.Task | None = None
_client = None                   # telethon.TelegramClient una vez arrancado
_inbox: list[dict] = []          # buffer de entrantes pendientes de triar (batching)
_seen: set[str] = set()          # messageIds ya mostrados (no resucitar lo que el operador quitó)
_mark_inbox = None               # v2 stateless: suscripción a msg.mark_read (creada en el loop, ver ingest.py)


def enabled() -> bool:
    return config.enabled()


def _set_status(status: str, qr=None) -> None:
    try:
        if ingest.v2_enabled():
            ingest.publish_status("telegram", status, qr)   # stateless: el widget refleja estado+QR
        else:
            store.set_platform_status("telegram", status, qr)
    except Exception as e:
        logger.debug(f"Telegram set_status: {e}")


def _qr_datauri(url: str) -> str | None:
    """QR (data-URI PNG) del tg://login URL, con segno (pura Python, PNG nativo — sin PIL). El widget pinta <img>."""
    try:
        import segno
        buf = io.BytesIO()
        segno.make(url, error="m").save(buf, kind="png", scale=6, border=2)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        logger.warning(f"Telegram: no pude generar el QR: {e}")
        return None


def _ensure_deps() -> bool:
    """Auto-instala telethon+segno si faltan (mismo espíritu que el self-heal del bridge de WhatsApp). Best-effort;
    devuelve True si el import funciona tras el intento."""
    try:
        import telethon  # noqa: F401
        import segno      # noqa: F401
        return True
    except ImportError:
        logger.warning("Telegram: faltan deps (telethon/segno) — intentando instalar (make install-telegram)…")
        try:
            import subprocess
            import sys
            subprocess.run([sys.executable, "-m", "pip", "install", "telethon", "segno"],
                           check=True, capture_output=True)
            import importlib
            importlib.invalidate_caches()
            import telethon  # noqa: F401
            import segno      # noqa: F401
            return True
        except Exception as e:
            logger.error(f"Telegram: no pude instalar deps automáticamente: {e}. Ejecuta: make install-telegram")
            return False


async def _normalize(event) -> dict:
    """events.NewMessage → dict que el triaje entiende ({senderName, chatName?, isGroup, body} + ids)."""
    from telethon import utils
    msg = event.message
    is_group = bool(event.is_group or event.is_channel)
    try:
        sender = await event.get_sender()
    except Exception:
        sender = None
    sender_name = (utils.get_display_name(sender) if sender else "") or "?"
    chat_name = None
    if is_group:
        try:
            chat_name = utils.get_display_name(await event.get_chat()) or "grupo"
        except Exception:
            chat_name = "grupo"
    chat_id = event.chat_id
    return {
        "senderName": sender_name, "chatName": chat_name, "isGroup": is_group,
        "body": event.raw_text or "",
        "messageId": f"{chat_id}:{msg.id}",          # único global (id de Telegram es por-chat)
        "chatId": chat_id, "senderId": getattr(sender, "id", None),
    }


async def _drain_inbox() -> None:
    if not _inbox:
        return
    batch = _inbox[:]
    _inbox.clear()
    if ingest.v2_enabled():
        # STATELESS: publicar los entrantes al bus (eventos ya nuevos, sin re-publicación) — triaje en el widget.
        for m in batch:
            ingest.publish_msg("telegram", m)
        return
    verdicts = await triage.classify(batch, config.operator_name())
    surfaced = notify.surface(verdicts, _seen)
    if not surfaced:
        return
    for v in surfaced:
        _seen.add(v.get("messageId"))
    store.upsert_items("telegram", surfaced)
    logger.info(f"Telegram: +{len(surfaced)} para ti")
    await notify.announce("Telegram", surfaced)


async def _drain_reads() -> None:
    v2 = ingest.v2_enabled()
    keys = (_mark_inbox.drain() if _mark_inbox else []) if v2 else store.take_pending_read("telegram")
    if not keys:
        return
    failed = []
    for k in keys:
        try:
            await _client.send_read_acknowledge(int(k["chatId"]))   # marca leído el chat hasta el último
        except Exception as e:
            logger.warning(f"Telegram mark-read falló (reintento luego): {e}")
            failed.append(k)
    if failed:
        if v2:
            for k in failed:                     # re-publicar al bus → reintento en el siguiente tick
                ingest.publish_mark_read(k)
        else:
            store.requeue_pending_read(failed)


async def _login_qr() -> bool:
    """Login por QR (Telethon). Pinta el QR en el widget y lo refresca al caducar. Devuelve True si autoriza.
    2FA (contraseña) queda fuera de alcance → se registra y se pide al operador desactivarla o loguear a mano."""
    from telethon.errors import SessionPasswordNeededError
    qr = await _client.qr_login()
    while True:
        _set_status("connecting", _qr_datauri(qr.url))
        try:
            await qr.wait(timeout=30)
            return True
        except asyncio.TimeoutError:
            try:
                await qr.recreate()                                 # el QR caducó → uno nuevo
            except Exception:
                qr = await _client.qr_login()
        except SessionPasswordNeededError:
            logger.error("Telegram: la cuenta tiene 2FA (contraseña). El login por QR no la cubre — "
                         "desactívala temporalmente o loguea a mano una vez; luego la sesión persiste.")
            _set_status("no_creds", None)
            return False
        except Exception as e:
            logger.warning(f"Telegram QR login: {e}")
            await asyncio.sleep(3)


async def _loop() -> None:
    global _client
    if not _ensure_deps():
        _set_status("off", None)
        return
    from telethon import TelegramClient, events

    config.session_dir().mkdir(parents=True, exist_ok=True)
    _set_status("starting", None)
    _client = TelegramClient(config.session_path(), config.api_id(), config.api_hash())
    try:
        await _client.connect()
    except Exception as e:
        logger.error(f"Telegram: no pude conectar: {e}")
        _set_status("off", None)
        return

    if not await _client.is_user_authorized():
        if not await _login_qr():
            return
    logger.info("Telegram conectado — escuchando tu buzón")

    @_client.on(events.NewMessage(incoming=True))
    async def _on_msg(event):                                       # noqa: ANN001
        try:
            _inbox.append(await _normalize(event))
        except Exception as e:
            logger.debug(f"Telegram normalize: {e}")

    global _mark_inbox
    if ingest.v2_enabled() and _mark_inbox is None:
        _mark_inbox = ingest.MarkReadInbox("telegram")   # suscripción en ESTE loop (server) → entrega directa
    _set_status("connected", None)
    # Telethon despacha los updates solo mientras el loop corre; esta tarea de batching coexiste con esa entrega.
    while True:
        await asyncio.sleep(config.batch_interval())
        if not _client.is_connected():
            try:
                await _client.connect()
            except Exception:
                _set_status("connecting", None)
                continue
        try:
            await _drain_inbox()
        except Exception as e:
            logger.debug(f"Telegram inbox tick: {e}")
        try:
            await _drain_reads()
        except Exception as e:
            logger.debug(f"Telegram reads tick: {e}")


def start() -> None:
    """Arranca el motor como tarea de fondo (llamar desde el lifespan del server si TG_ENABLED=1)."""
    global _task
    if not enabled():
        _set_status("off", None)
        logger.info("Telegram: desactivado (TG_ENABLED!=1)")
        return
    if not config.has_credentials():
        _set_status("no_creds", None)
        logger.warning("Telegram: faltan TG_API_ID/TG_API_HASH en .env (sácalos de my.telegram.org). "
                       "El widget mostrará 'faltan credenciales'.")
        return
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info("Telegram: motor arrancado")


async def stop() -> None:
    global _task, _client
    if _task:
        _task.cancel()
        _task = None
    if _client is not None:
        try:
            await _client.disconnect()
        except Exception:
            pass
        _client = None
