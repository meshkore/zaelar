#
# inbound.py — what the account RECEIVES: the normalised event (media captured), the inbound batch, the operator's
# own outgoing messages and the chats he read elsewhere. Buffers and connection are read from the facade at call time.
#
from loguru import logger

from connectors.messaging import ingest, notify, store, triage
from connectors.telegram import config
from connectors.telegram import service as _svc

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
    if not _svc._inbox:
        return
    batch = _svc._inbox[:]
    _svc._inbox.clear()
    if ingest.v2_enabled():
        # STATELESS: publish inbound messages to the bus (already-new events, no re-publication) — triage in widget.
        for m in batch:
            ingest.publish_msg("telegram", m)
        return
    verdicts = await triage.classify(batch, config.operator_name())
    # V2-607 — the direct path splits the same two questions as the v2 owner: what is NEW goes into his
    # inbox, and only then is a notice considered. Before, `notify.surface` decided BOTH, so flipping the
    # notification default to silence would have left this path storing nothing at all — a connected
    # channel showing an empty list, which is the exact failure V2-606 had just fixed.
    fresh = store.new_among(store.load(), "telegram", verdicts)
    if not fresh:
        return
    for v in fresh:
        _svc._seen.add(v.get("messageId"))
    store.upsert_items("telegram", fresh)
    notice = notify.deserving(fresh)
    logger.info(f"Telegram: +{len(fresh)} ({len(notice)} avisan)")
    if notice:
        await notify.announce("Telegram", notice)


async def _drain_outbox() -> None:
    """Messages the OPERATOR sent from his own Telegram (V2-546). They go to `connector.msg_out`, never to
    `connector.msg`: that topic feeds triage and proactive notification, and being told about one's own message
    is neither news nor a decision. The widget appends them to the conversation and treats the chat as seen."""
    if not _svc._outbox:
        return
    batch, _svc._outbox[:] = _svc._outbox[:], []
    if not ingest.v2_enabled():
        return                                   # legacy direct path never had a conversation to append to
    for m in batch:
        ingest.publish_msg_out("telegram", m)


async def _drain_read_marks() -> None:
    """Chats the operator read on another device. Telegram's update is a WATERMARK (`max_id`), so it is resolved
    to that message's DATE — the store speaks time, which is the only vocabulary all three platforms share.

    If the date cannot be resolved the read is DROPPED, not widened to the whole chat: not marking costs one
    stale row the operator can clear himself, marking too much hides mail he has never seen."""
    if not _svc._reads or not ingest.v2_enabled():
        _svc._reads.clear()
        return
    batch, _svc._reads[:] = _svc._reads[:], []
    seen: dict[int, int] = {}
    for r in batch:                              # one watermark per chat: the highest wins
        cid, mid = r.get("chatId"), r.get("maxId") or 0
        if cid is not None and mid >= seen.get(cid, -1):
            seen[cid] = mid
    for chat_id, max_id in seen.items():
        try:
            msg = await _svc._client.get_messages(chat_id, ids=max_id)
            ts = msg.date.timestamp() if msg is not None else None
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Telegram read watermark {chat_id}/{max_id}: {e}")
            continue
        if ts is None:
            continue
        ingest.publish_read("telegram", chat_id, upto_ts=ts)
