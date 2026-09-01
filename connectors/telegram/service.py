#
# service.py — Telegram connector ENGINE integrated into zaelar (INI-015). Runs IN-PROCESS in the server lifespan
# (gated by TG_ENABLED, always-on), as an asyncio task — Telethon is a pure asyncio client, with NO Node subprocess
# or bridge to vendor (unlike WhatsApp). Telegram is "black-box lib": a third-party library (Telethon), with no Hermes
# dependency.
#
# Flow: QR login (client.qr_login(), QR rendered IN THE WIDGET via segno) -> listen to events.NewMessage -> classify
# with the SHARED LOCAL model (connectors/messaging/triage) -> write the UNIFIED store
# (widgets/_data/mensajeria.json, platform="telegram") -> drain pending_read by marking read (send_read_acknowledge).
# The classifier does NOT go through the Hermes agent (privacy + voice ACP invariant). Read-only + mark-read.
#
import asyncio
import base64
import io

from loguru import logger

from connectors.messaging import ingest, notify, store, triage
from connectors.telegram import config

_task: asyncio.Task | None = None
_client = None                   # telethon.TelegramClient once started
_inbox: list[dict] = []          # inbound buffer pending triage (batching)
_seen: set[str] = set()          # already shown messageIds (do not resurrect what the operator removed)
_mark_inbox = None               # v2 stateless: msg.mark_read subscription (created in the loop; see ingest.py)
_reply_inbox = None              # V2-521: msg.reply subscription (created in the loop)


def enabled() -> bool:
    return config.enabled()


def _set_status(status: str, qr=None) -> None:
    try:
        if ingest.v2_enabled():
            ingest.publish_status("telegram", status, qr)   # stateless: widget reflects state+QR
        else:
            store.set_platform_status("telegram", status, qr)
    except Exception as e:
        logger.debug(f"Telegram set_status: {e}")


def _qr_datauri(url: str) -> str | None:
    """QR (PNG data-URI) for the tg://login URL, with segno (pure Python, native PNG — no PIL). Widget renders <img>."""
    try:
        import segno
        buf = io.BytesIO()
        segno.make(url, error="m").save(buf, kind="png", scale=6, border=2)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        logger.warning(f"Telegram: no pude generar el QR: {e}")
        return None


def _ensure_deps() -> bool:
    """Auto-install telethon+segno if missing (same spirit as WhatsApp bridge self-heal). Best-effort; returns True
    if import works after the attempt."""
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


# ── Media capture (V2-543) ──────────────────────────────────────────────────
# Telegram used to capture NOTHING for media: a photo with no caption arrived as an empty bubble
# (`event.raw_text or ""`) — worse than WhatsApp, which at least had a placeholder. MTProto gives the bytes in
# one call; they land in the messaging widget's own data dir so `GET /widgets/mensajeria/asset/{name}` can
# serve them. A file over the cap is not downloaded (the type still travels, so the widget says WHAT it is).
_TG_MEDIA_MAX_BYTES = 20 * 1024 * 1024


def _media_dir() -> str:
    from widgets import store as wstore
    return wstore.data_dir("mensajeria")


def _tg_media_type(msg) -> str | None:
    """Same vocabulary as the WhatsApp bridge (image|video|audio|ptt|document), so the store and the widget
    read ONE set of values."""
    if getattr(msg, "photo", None) is not None:
        return "image"
    if getattr(msg, "voice", None) is not None:
        return "ptt"
    if getattr(msg, "video", None) is not None or getattr(msg, "video_note", None) is not None:
        return "video"
    if getattr(msg, "audio", None) is not None:
        return "audio"
    if getattr(msg, "document", None) is not None:
        return "document"
    if getattr(msg, "media", None) is not None:
        return "document"
    return None


async def _capture_media(msg, chat_id) -> tuple[str | None, list[str]]:
    mtype = _tg_media_type(msg)
    if mtype is None:
        return None, []
    try:
        size = int(getattr(getattr(msg, "file", None), "size", 0) or 0)
        if size > _TG_MEDIA_MAX_BYTES:
            return mtype, []                       # too big: say what it is, do not pull the bytes
        import os
        base = os.path.join(_media_dir(), f"tg_{chat_id}_{msg.id}")
        path = await msg.download_media(file=base)  # telethon appends the right extension
        return mtype, ([str(path)] if path else [])
    except Exception as e:
        logger.debug(f"Telegram media: {e}")
        return mtype, []


async def _normalize(event) -> dict:
    """events.NewMessage -> dict understood by triage ({senderName, chatName?, isGroup, body} + ids)."""
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
    media_type, media_paths = await _capture_media(msg, chat_id)
    body = event.raw_text or ""
    if not body and media_type:
        body = f"[{media_type} received]"           # the WhatsApp bridge's exact placeholder, one vocabulary
    out = {
        "senderName": sender_name, "chatName": chat_name, "isGroup": is_group,
        "body": body,
        "messageId": f"{chat_id}:{msg.id}",          # globally unique (Telegram id is per-chat)
        "chatId": chat_id, "senderId": getattr(sender, "id", None),
    }
    try:
        out["timestamp"] = msg.date.timestamp()
    except Exception:
        pass
    if media_type:
        out["hasMedia"] = True
        out["mediaType"] = media_type
        out["mediaUrls"] = media_paths
    return out


async def _drain_inbox() -> None:
    if not _inbox:
        return
    batch = _inbox[:]
    _inbox.clear()
    if ingest.v2_enabled():
        # STATELESS: publish inbound messages to the bus (already-new events, no re-publication) — triage in widget.
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


def _tg_msg_id(raw) -> int | None:
    """Our wire messageId is the composite '<chat_id>:<msg_id>' (service-made, `_normalize`). The per-chat
    Telegram id is the part AFTER the colon. int('<chat>:<id>') raises — which is exactly how replies silently
    lost their threading (V2-543: `reply_to` always fell back to None) and mark-read ignored the message."""
    s = str(raw or "")
    part = s.rsplit(":", 1)[-1] if ":" in s else s
    try:
        return int(part)
    except (TypeError, ValueError):
        return None


async def _drain_reads() -> None:
    v2 = ingest.v2_enabled()
    keys = (_mark_inbox.drain() if _mark_inbox else []) if v2 else store.take_pending_read("telegram")
    if not keys:
        return
    failed = []
    for k in keys:
        try:
            # Precise watermark (V2-543): as a USER account this genuinely propagates. max_id marks read UP TO
            # that message; with no parseable id it degrades to the old whole-chat acknowledge (max_id=None).
            await _client.send_read_acknowledge(int(k["chatId"]), max_id=_tg_msg_id(k.get("messageId")))
        except Exception as e:
            logger.warning(f"Telegram mark-read falló (reintento luego): {e}")
            failed.append(k)
    if failed:
        if v2:
            for k in failed:                     # re-publish to bus -> retry on next tick
                ingest.publish_mark_read(k)
        else:
            store.requeue_pending_read(failed)


async def _drain_replies() -> None:
    """Drain dictated replies (V2-521 — same seam the email connector has had since V2-051; Telegram only
    ever read). The widget already enqueued mark-read for the original, so this only SENDS. A failure is
    TOLD to the operator and not requeued — one honest "no pude enviarlo" beats a send retried forever."""
    if not ingest.v2_enabled() or _reply_inbox is None:
        return
    for r in _reply_inbox.drain():
        text = (r.get("text") or "").strip()
        try:
            chat_id = int(r.get("chatId"))
        except (TypeError, ValueError):
            continue
        if not text:
            continue
        reply_to = _tg_msg_id(r.get("messageId"))   # composite-aware: replies land THREADED, not loose
        try:
            await _client.send_message(chat_id, text, reply_to=reply_to)
            logger.info(f"Telegram: respuesta enviada a {chat_id}")
            _note(f"[SISTEMA] Telegram enviado a {r.get('to') or chat_id}. Confírmaselo al operador de forma natural.")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Telegram: fallo al enviar a {chat_id}: {e}")
            _note(f"[SISTEMA] No se pudo enviar el Telegram a {r.get('to') or chat_id} ({e}). Avísale al operador.")


def _note(text: str) -> None:
    try:
        from voice import brain_notes
        brain_notes.push(text)
    except Exception:
        pass


async def _login_qr() -> bool:
    """QR login (Telethon). Render QR in the widget and refresh it on expiry. Returns True if authorized.
    2FA (password) is out of scope -> log it and ask the operator to disable it or log in manually."""
    from telethon.errors import SessionPasswordNeededError
    qr = await _client.qr_login()
    while True:
        _set_status("connecting", _qr_datauri(qr.url))
        try:
            await qr.wait(timeout=30)
            return True
        except asyncio.TimeoutError:
            try:
                await qr.recreate()                                 # QR expired -> new one
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

    global _mark_inbox, _reply_inbox
    if ingest.v2_enabled() and _mark_inbox is None:
        _mark_inbox = ingest.MarkReadInbox("telegram")   # subscription in THIS loop (server) -> direct delivery
    if ingest.v2_enabled() and _reply_inbox is None:
        _reply_inbox = ingest.ReplyInbox("telegram")     # V2-521: dictated replies, same delivery path
    _set_status("connected", None)
    # Telethon dispatches updates only while the loop runs; this batching task coexists with that delivery.
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
        try:
            await _drain_replies()
        except Exception as e:
            logger.debug(f"Telegram replies tick: {e}")


def start() -> None:
    """Start the engine as a background task (call from server lifespan if TG_ENABLED=1)."""
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
