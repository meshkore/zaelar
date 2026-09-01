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
_outbox: list[dict] = []         # V2-546: messages the OPERATOR sent from his own Telegram (no triage)
_reads: list[dict] = []          # V2-546: chats he read elsewhere ({chatId, maxId})
_seen: set[str] = set()          # already shown messageIds (do not resurrect what the operator removed)
_mark_inbox = None               # v2 stateless: msg.mark_read subscription (created in the loop; see ingest.py)
_reply_inbox = None              # V2-521: msg.reply subscription (created in the loop)
_history_inbox = None            # V2-546: msg.history subscription (created in the loop)


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


async def _drain_outbox() -> None:
    """Messages the OPERATOR sent from his own Telegram (V2-546). They go to `connector.msg_out`, never to
    `connector.msg`: that topic feeds triage and proactive notification, and being told about one's own message
    is neither news nor a decision. The widget appends them to the conversation and treats the chat as seen."""
    if not _outbox:
        return
    batch, _outbox[:] = _outbox[:], []
    if not ingest.v2_enabled():
        return                                   # legacy direct path never had a conversation to append to
    for m in batch:
        ingest.publish_msg_out("telegram", m)


async def _drain_read_marks() -> None:
    """Chats the operator read on another device. Telegram's update is a WATERMARK (`max_id`), so it is resolved
    to that message's DATE — the store speaks time, which is the only vocabulary all three platforms share.

    If the date cannot be resolved the read is DROPPED, not widened to the whole chat: not marking costs one
    stale row the operator can clear himself, marking too much hides mail he has never seen."""
    if not _reads or not ingest.v2_enabled():
        _reads.clear()
        return
    batch, _reads[:] = _reads[:], []
    seen: dict[int, int] = {}
    for r in batch:                              # one watermark per chat: the highest wins
        cid, mid = r.get("chatId"), r.get("maxId") or 0
        if cid is not None and mid >= seen.get(cid, -1):
            seen[cid] = mid
    for chat_id, max_id in seen.items():
        try:
            msg = await _client.get_messages(chat_id, ids=max_id)
            ts = msg.date.timestamp() if msg is not None else None
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Telegram read watermark {chat_id}/{max_id}: {e}")
            continue
        if ts is None:
            continue
        ingest.publish_read("telegram", chat_id, upto_ts=ts)


async def _drain_history() -> None:
    """Serve "load previous" for one chat (V2-546). MTProto gives arbitrary history from the account itself, so
    Telegram is the one platform where this is exact: `offset_id` walks strictly BACKWARDS from the oldest
    message we hold. Fewer results than asked for means we reached the start of the conversation — that is what
    lets the widget stop offering the button instead of asking forever."""
    if _history_inbox is None:
        return
    for order in _history_inbox.drain():
        chat_id = order.get("chatId")
        try:
            limit = max(1, min(100, int(order.get("limit") or 30)))
        except (TypeError, ValueError):
            limit = 30
        offset_id = _tg_msg_id(order.get("beforeId")) or 0
        try:
            msgs = await _client.get_messages(int(chat_id), limit=limit, offset_id=offset_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Telegram historial de {chat_id}: {e}")
            ingest.publish_history("telegram", chat_id, [], error=str(e))
            continue
        out = []
        for m in msgs or []:
            out.append(await _history_entry(m, chat_id))
        ingest.publish_history("telegram", chat_id, out, complete=len(msgs or []) < limit)
        logger.info(f"Telegram: +{len(out)} mensajes anteriores de {chat_id}")


async def _history_entry(msg, chat_id) -> dict:
    """One historical message in the conversation's shape. Media is NOT downloaded here: a "load previous" can
    pull thirty messages at once and paying for thirty downloads to fill a scrollback is the wrong trade — the
    TYPE still travels, so the widget says what it was."""
    from telethon import utils
    try:
        sender = await msg.get_sender()
        who = utils.get_display_name(sender) or "?"
    except Exception:  # noqa: BLE001
        who = "?"
    mtype = _tg_media_type(msg)
    body = (msg.message or "") or (f"[{mtype} received]" if mtype else "")
    mine = bool(getattr(msg, "out", False))
    entry = {
        "messageId": f"{chat_id}:{msg.id}", "dir": "out" if mine else "in",
        # An empty `from` on an outbound message is deliberate: the thread module owns how the operator is
        # labelled, and a second copy of that string here is one more thing to keep in step for no gain.
        "from": "" if mine else who,
        "body": body, "read": True,
    }
    try:
        entry["ts"] = msg.date.timestamp()
    except Exception:  # noqa: BLE001
        pass
    if mtype:
        entry["mediaType"] = mtype
    return entry


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

    # V2-546 — the account is the SAME account the operator uses on his phone, so Telethon already sees
    # everything he does there. These two updates were simply never subscribed to.
    @_client.on(events.NewMessage(outgoing=True))
    async def _on_msg_out(event):                                   # noqa: ANN001
        try:
            m = await _normalize(event)
            m["from"] = ""                                          # the thread module names the operator
            _outbox.append(m)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Telegram normalize (saliente): {e}")

    @_client.on(events.MessageRead(inbox=True))
    async def _on_read(event):                                      # noqa: ANN001
        # inbox=True is "I read THEIR messages" (on any device). The outbox variant — someone read MINE — is
        # deliberately not subscribed: it says nothing about what still wants the operator's attention.
        try:
            _reads.append({"chatId": event.chat_id, "maxId": int(getattr(event, "max_id", 0) or 0)})
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Telegram read receipt: {e}")

    global _mark_inbox, _reply_inbox, _history_inbox
    if ingest.v2_enabled() and _mark_inbox is None:
        _mark_inbox = ingest.MarkReadInbox("telegram")   # subscription in THIS loop (server) -> direct delivery
    if ingest.v2_enabled() and _reply_inbox is None:
        _reply_inbox = ingest.ReplyInbox("telegram")     # V2-521: dictated replies, same delivery path
    if ingest.v2_enabled() and _history_inbox is None:
        _history_inbox = ingest.HistoryAskInbox("telegram")   # V2-546: "load previous"
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
        for what, fn in (("outbox", _drain_outbox), ("read marks", _drain_read_marks),
                         ("history", _drain_history)):
            try:
                await fn()
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Telegram {what} tick: {e}")


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
