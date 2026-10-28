#
# history.py — the account's PAST and read state: «load previous», the platform-wide pull, mark-read, and the
# composite message id they parse. Connection and inboxes are read from the facade at call time.
#
from loguru import logger

from connectors.messaging import ingest, store
from connectors.telegram import service as _svc


async def _drain_history() -> None:
    """Serve "load previous" for one chat (V2-546). MTProto gives arbitrary history from the account itself, so
    Telegram is the one platform where this is exact: `offset_id` walks strictly BACKWARDS from the oldest
    message we hold. Fewer results than asked for means we reached the start of the conversation — that is what
    lets the widget stop offering the button instead of asking forever."""
    if _svc._history_inbox is None:
        return
    for order in _svc._history_inbox.drain():
        chat_id = order.get("chatId")
        try:
            limit = max(1, min(100, int(order.get("limit") or 30)))
        except (TypeError, ValueError):
            limit = 30
        offset_id = _tg_msg_id(order.get("beforeId")) or 0
        if offset_id and order.get("includeAnchor"):
            offset_id += 1                 # a chat opened from the list: its last message is the anchor itself
        try:
            msgs = await _svc._client.get_messages(int(chat_id), limit=limit, offset_id=offset_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Telegram historial de {chat_id}: {e}")
            ingest.publish_history("telegram", chat_id, [], error=str(e))
            continue
        out = []
        for m in msgs or []:
            out.append(await _svc._history_entry(m, chat_id))
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
    mtype = _svc._tg_media_type(msg)
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


async def _drain_fetch() -> None:
    """Serve a platform-wide pull (V2-624 — «chupar más mensajes», «la actividad de las últimas 72 horas»).
    Telegram is the platform where this is EXACT: the account enumerates its own dialogs, so «conversations
    with movement in the window» is a real query, not an approximation. Broadcast channels are excluded on
    purpose — a channel is a feed, not a conversation the operator has. Everything lands in the CONVERSATIONS
    as read scrollback via the same connector.history seam "load previous" uses — never in triage: pulling
    the past must not interrupt anybody. Caps: 60 dialogs walked, 20 messages per chat, so a busy account
    cannot turn one voice order into thousands of fetches."""
    if _svc._fetch_inbox is None:
        return
    for order in _svc._fetch_inbox.drain():
        try:
            hours = max(1.0, float(order.get("since_hours") or 72))
        except (TypeError, ValueError):
            hours = 72.0
        import datetime as _dt
        cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours)
        chats = total = 0
        try:
            async for dialog in _svc._client.iter_dialogs(limit=60):
                # A stale dialog is SKIPPED, never a reason to stop: Telegram floats PINNED dialogs to the
                # top of the list, so "newest-first" does not hold at the head — a pinned chat idle for
                # months arrives FIRST, and breaking on it ends the walk before any real activity is seen
                # (measured live 2026-09-09: a 72h fetch answered 0 over an account whose newest message
                # was 12 minutes old). The limit already bounds the cost; get_messages only runs for the
                # dialogs that pass.
                if dialog.date is None or dialog.date < cutoff:
                    continue
                if dialog.is_channel and not dialog.is_group:
                    continue                 # broadcast feed, not a conversation
                msgs = await _svc._client.get_messages(dialog.entity, limit=20)
                rows = []
                for m in msgs or []:
                    try:
                        if m.date is None or m.date < cutoff:
                            continue
                    except TypeError:
                        continue
                    rows.append(await _svc._history_entry(m, dialog.id))
                if not rows:
                    continue
                ingest.publish_history("telegram", dialog.id, rows,
                                       name=dialog.name or "", is_group=bool(dialog.is_group))
                chats += 1
                total += len(rows)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Telegram fetch: {e}")
            _svc._note(f"[SISTEMA] La traída de Telegram falló ({e}). Díselo al operador.")
            continue
        logger.info(f"Telegram: fetch de {hours:.0f}h → {total} mensajes en {chats} conversación(es)")
        _svc._note(f"[SISTEMA] Traída de Telegram hecha: {total} mensaje(s) de las últimas {hours:.0f} h en "
                   f"{chats} conversación(es), ya en el widget de mensajería. Cuéntaselo al operador."
                   if total else
                   f"[SISTEMA] Traída de Telegram hecha: no hay conversaciones con actividad en las últimas "
                   f"{hours:.0f} h. Díselo al operador tal cual.")


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
    keys = (_svc._mark_inbox.drain() if _svc._mark_inbox else []) if v2 else store.take_pending_read("telegram")
    if not keys:
        return
    failed = []
    for k in keys:
        try:
            # Precise watermark (V2-543): as a USER account this genuinely propagates. max_id marks read UP TO
            # that message; with no parseable id it degrades to the old whole-chat acknowledge (max_id=None).
            await _svc._client.send_read_acknowledge(int(k["chatId"]), max_id=_tg_msg_id(k.get("messageId")))
        except Exception as e:
            logger.warning(f"Telegram mark-read falló (reintento luego): {e}")
            failed.append(k)
    if failed:
        if v2:
            for k in failed:                     # re-publish to bus -> retry on next tick
                ingest.publish_mark_read(k)
        else:
            store.requeue_pending_read(failed)
