#
# account_ops.py — what the operator does with his Telegram ACCOUNT beyond reading and replying: the chat list
# (`msg.chats`), creating a group (`msg.group`), «mark as unread» (`msg.mark_unread`), sending files, and the history
# walk's tick. Extracted from service.py when it crossed the size ratchet — split along a real seam, never a
# raised ceiling. Every function reads the connection and the inboxes from `service` AT CALL TIME (`_svc.…`), so
# the loop that owns them, and a test that replaces them, stay the single source.
#
import time

from loguru import logger

from connectors.messaging import ingest, store
from connectors.telegram import service as _svc


async def _drain_unread() -> None:
    """Put dialogs back to unread («déjalo como no leído»), as the app's «Mark as unread» does."""
    if _svc._unread_inbox is None:
        return
    from telethon.tl.functions.messages import MarkDialogUnreadRequest
    from telethon.tl.types import InputDialogPeer
    for k in _svc._unread_inbox.drain():
        try:
            peer = await _svc._client.get_input_entity(int(k.get("chatId")))
            await _svc._client(MarkDialogUnreadRequest(peer=InputDialogPeer(peer), unread=True))
            logger.info(f"Telegram: chat {k.get('chatId')} marcado como no leído")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Telegram: no pude marcar como no leído {k.get('chatId')}: {e}")
            _svc._note(f"[SISTEMA] No pude dejar como no leído ese chat de Telegram ({e}). Díselo al operador.")


async def _drain_groups() -> None:
    """Create the groups the operator asked for, as Telegram's «New group» does today: a supergroup with these
    people invited. Members arrive resolved (an id we hold, or a @username / phone Telethon resolves)."""
    if _svc._group_inbox is None:
        return
    from telethon.tl.functions.channels import CreateChannelRequest, InviteToChannelRequest
    for order in _svc._group_inbox.drain():
        name = str(order.get("name") or "").strip()[:128]
        try:
            peers = []
            for m in order.get("members") or []:
                cid = str((m or {}).get("chatId") or "").strip()
                ref = int(cid) if cid.lstrip("-").isdigit() else str((m or {}).get("to") or "").strip()
                if ref:
                    peers.append(await _svc._client.get_input_entity(ref))
            res = await _svc._client(CreateChannelRequest(title=name, about="", megagroup=True))
            channel = res.chats[0]
            if peers:
                await _svc._client(InviteToChannelRequest(channel, peers))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Telegram: no pude crear el grupo {name}: {e}")
            ingest.publish_send_failed(order, str(e))
            _svc._note(f"[SISTEMA] No pude crear el grupo de Telegram «{name}» ({e}). Díselo al operador.")
            continue
        from telethon import utils
        gid = utils.get_peer_id(channel)
        logger.info(f"Telegram: grupo creado {gid} con {len(peers)} miembro(s)")
        ingest.publish_chats("telegram", [{"chatId": str(gid), "name": name, "kind": "group",
                                            "ts": time.time(), "preview": ""}])
        text, files = str(order.get("text") or "").strip(), order.get("attachments") or []
        if text or files:
            try:
                await _send(gid, text, files)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Telegram: grupo creado, primer mensaje no enviado: {e}")
        _svc._note(f"[SISTEMA] Grupo de Telegram «{name}» creado con {len(peers)} persona(s). Díselo al operador.")


async def _walk_tick() -> None:
    """The history walk (backfill.py): one page per tick, on its own task."""
    from connectors.telegram import backfill as _backfill
    await _backfill.walker.tick(_svc._client)


def _dialog_row(dialog) -> dict:
    """One dialog in the platform-agnostic shape of `ingest.publish_chats`."""
    msg = dialog.message
    mtype = _svc._tg_media_type(msg) if msg is not None else None
    kind = "channel" if dialog.is_channel and not dialog.is_group else ("group" if dialog.is_group else "person")
    muted = False
    try:
        until = dialog.dialog.notify_settings.mute_until
        muted = bool(until) and (until.timestamp() if hasattr(until, "timestamp") else float(until)) > time.time()
    except Exception as e:  # noqa: BLE001 — a dialog without notify settings is simply not muted
        logger.debug(f"Telegram dialog mute state unreadable: {type(e).__name__}")
    return {"chatId": str(dialog.id), "name": dialog.name or "", "kind": kind,
            "unread": int(dialog.unread_count or 0), "ts": dialog.date.timestamp() if dialog.date else 0.0,
            "preview": ((getattr(msg, "message", "") or "") if msg is not None else "")[:160],
            "mediaType": mtype or "", "fromMe": bool(getattr(msg, "out", False)),
            "archived": bool(getattr(dialog, "archived", False)), "pinned": bool(dialog.pinned), "muted": muted,
            "forum": bool(getattr(dialog.entity, "forum", False)),
            "lastId": str(getattr(msg, "id", "") or "")}


async def _drain_chats() -> None:
    """Serve one page of the chat list. Telegram lists the account's dialogs exactly, so this walks the real
    list, newest first, `before` (unix seconds) as the offset. Pinned dialogs float to the head of the FIRST
    page whatever their age, so the cursor for the next page is the oldest UNPINNED dialog seen, not the last
    row — or every pinned chat would push the next page back to the date it was last used."""
    if _svc._chats_inbox is None:
        return
    import datetime as _dt
    for order in _svc._chats_inbox.drain():
        before = order.get("before")
        try:
            limit = max(1, min(100, int(order.get("limit") or 20)))
        except (TypeError, ValueError):
            limit = 20
        offset = _dt.datetime.fromtimestamp(float(before), _dt.timezone.utc) if before else None
        rows, cursor = [], None
        try:
            async for dialog in _svc._client.iter_dialogs(limit=limit, offset_date=offset):
                rows.append(_dialog_row(dialog))
                if not dialog.pinned and dialog.date is not None:
                    cursor = dialog.date.timestamp()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Telegram chat list: {e}")
            ingest.publish_chats("telegram", rows, before=before, error=str(e))
            continue
        ingest.publish_chats("telegram", rows, before=before, next_before=cursor, complete=len(rows) < limit)
        logger.info(f"Telegram: chat list page → {len(rows)} dialog(s)")


async def _send(peer, text: str, files: list[str], reply_to=None):
    """One message as the native app sends it: the files (several photos/videos go as ONE album, the text as
    its caption), a voice note as a voice note, or the text alone. Returns the last sent Message. The one
    Telethon seam every send and reply crosses, so the connector call is recorded here (`calls.sent`)."""
    import time as _t
    from connectors.messaging import calls as _calls
    t0 = _t.monotonic()
    op = "reply" if reply_to else "send"
    files = store.sendable(files)
    try:
        sent = await _send_parts(peer, text, files, reply_to)
    except Exception as e:
        _calls.sent("telegram", op, ok=False, ms=int((_t.monotonic() - t0) * 1000), to=peer, files=len(files),
                    error=f"{type(e).__name__}: {e}")
        raise
    _calls.sent("telegram", op, ok=True, ms=int((_t.monotonic() - t0) * 1000), to=peer, files=len(files))
    return sent


async def _send_parts(peer, text: str, files: list[str], reply_to=None):
    if not files:
        return await _svc._client.send_message(peer, text, reply_to=reply_to, parse_mode=None)
    voice = [f for f in files if store.kind_of(f) == "ptt"]
    rest = [f for f in files if f not in voice]
    sent = None
    if rest:
        sent = await _svc._client.send_file(peer, rest if len(rest) > 1 else rest[0], caption=text or None,
                                       reply_to=reply_to, parse_mode=None, force_document=False)
        if isinstance(sent, list):
            sent = sent[-1] if sent else None
    for f in voice:
        sent = await _svc._client.send_file(peer, f, voice_note=True, reply_to=reply_to)
    if text and not rest:
        sent = await _svc._client.send_message(peer, text, reply_to=reply_to, parse_mode=None)
    return sent
