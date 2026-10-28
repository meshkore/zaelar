#
# inbound.py — what the bridge HANDS US: new messages (scrollback, his own outgoing ones, the news that goes to
# triage), the chats he read on his phone, and «load previous» asked of the phone.
#
from loguru import logger

from connectors.messaging import ingest, notify, store, triage
from connectors.whatsapp import client, config
from connectors.whatsapp import service as _svc

PLATFORM = _svc.PLATFORM


def _origin(m: dict) -> tuple[str, str | None]:
    if m.get("isGroup"):
        return (m.get("senderName") or "?", m.get("chatName") or "grupo")
    return (m.get("senderName") or "?", None)


async def _ingest_new() -> None:
    msgs = await client.get_messages()
    if not msgs:
        return
    # V2-546 — scrollback the PHONE sent because we asked for it. It is not news: it goes straight to the
    # conversation, never through triage, or pressing "load previous" would interrupt the operator about
    # messages from weeks ago.
    backfill = [m for m in msgs if m.get("history")]
    msgs = [m for m in msgs if not m.get("history")]
    if backfill and ingest.v2_enabled():
        by_chat: dict[str, list[dict]] = {}
        for m in backfill:
            by_chat.setdefault(str(m.get("chatId")), []).append(m)
        for chat_id, rows in by_chat.items():
            ingest.publish_history(PLATFORM, chat_id, [_svc._history_entry(m) for m in rows])
    # The bridge also tags each message with its DIRECTION. An outbound one (the operator wrote from his own
    # phone, or zaelar sent it for him) must never reach triage or notification: it is not news and it is not a
    # decision. It goes to the conversation and marks that chat as seen.
    outgoing = [m for m in msgs if m.get("direction") == "out"]
    msgs = [m for m in msgs if m.get("direction") != "out"]
    if outgoing and ingest.v2_enabled():
        sent = 0
        for m in outgoing:
            mid = m.get("messageId")
            if mid and mid not in _svc._published:
                _svc._published.add(mid)
                m = dict(m)
                m["from"] = ""                    # the thread module names the operator
                ingest.publish_msg_out(PLATFORM, m)
                sent += 1
        # V2-616 — INFO, not debug: the whole outbound-capture path (his own phone joining the thread here)
        # had never once been observed live before this, and a silent success is indistinguishable from a
        # silent gap anywhere further down the chain (the owner's drain, the thread store). This is the ONE
        # line that proves the bridge itself actually saw the message.
        if sent:
            logger.info(f"WhatsApp: +{sent} outbound message(s) captured from the operator's phone")
    if not msgs:
        return
    if ingest.v2_enabled():
        # STATELESS: publish NEW messages to the bus (dedup by messageId before triage) — the messaging widget
        # triages, stores, and notifies. The connector does not triage or store state.
        for m in msgs:
            mid = m.get("messageId")
            if mid and mid not in _svc._published:
                _svc._published.add(mid)
                ingest.publish_msg(PLATFORM, m)
        return
    verdicts = await triage.classify(msgs, config.operator_name() or None)
    # V2-607 — the direct path splits the same two questions as the v2 owner: what is NEW goes into his
    # inbox, and only then is a notice considered. Before, `notify.surface` decided BOTH, so flipping the
    # notification default to silence would have left this path storing nothing at all — a connected
    # channel showing an empty list, which is the exact failure V2-606 had just fixed.
    fresh = store.new_among(store.load(), PLATFORM, verdicts)
    if not fresh:
        return
    for v in fresh:
        _svc._seen.add(v.get("messageId"))
        who, group = _origin(v)
        v["from"], v["group"] = who, group          # normalize to unified-store shape
    store.upsert_items(PLATFORM, fresh)
    notice = notify.deserving(fresh)
    logger.info(f"WhatsApp: +{len(fresh)} ({len(notice)} avisan)")
    if notice:
        await notify.announce("WhatsApp", notice)


def _history_entry(m: dict) -> dict:
    """A backfilled message in the conversation's shape. Read by definition — it is scrollback, not something
    demanding attention — and the operator is named by the thread module, not here."""
    mine = m.get("direction") == "out"
    entry = {
        "messageId": m.get("messageId"), "dir": "out" if mine else "in",
        "from": "" if mine else (m.get("senderName") or "?"),
        "body": m.get("body") or "", "read": True,
    }
    try:
        entry["ts"] = float(m.get("timestamp") or 0)
    except (TypeError, ValueError):
        pass
    if m.get("mediaType"):
        entry["mediaType"] = m.get("mediaType")
    return entry


async def _drain_external_reads() -> None:
    """Chats the operator read on his phone (V2-546). WhatsApp reports a per-chat COUNTER, so this is a
    whole-chat signal with no watermark — the bridge only queues one once that counter reaches zero, which is
    the only reading of it that cannot hide unseen messages."""
    if not ingest.v2_enabled():
        return
    for r in await client.get_reads():
        chat_id = r.get("chatId")
        if chat_id:
            ingest.publish_read(PLATFORM, chat_id)


async def _drain_history() -> None:
    """Serve "load previous" (V2-546). WhatsApp is the honest case of the three: history lives on the PHONE, so
    all we can do is ask it and wait — the messages come back as ordinary upserts on a later poll. A build or a
    phone that cannot serve it SAYS so, rather than leaving the operator pressing a button that does nothing."""
    if _svc._history_inbox is None:
        return
    for order in _svc._history_inbox.drain():
        chat_id, oldest = order.get("chatId"), order.get("beforeId")
        if not chat_id or not oldest:
            ingest.publish_history(PLATFORM, chat_id, [],
                                   error="no sé por dónde empieza lo que tengo de ese chat")
            continue
        try:
            ack = await client.fetch_history(str(chat_id), str(oldest), float(order.get("beforeTs") or 0),
                                             int(order.get("limit") or 30),
                                             oldest_from_me=bool(order.get("beforeFromMe")),
                                             include_anchor=bool(order.get("includeAnchor")))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"WhatsApp historial de {chat_id}: {e}")
            ingest.publish_history(PLATFORM, chat_id, [], error=str(e))
            continue
        if not (ack or {}).get("available"):
            ingest.publish_history(PLATFORM, chat_id, [],
                                   error=(ack or {}).get("error") or "tu WhatsApp no me deja pedir el histórico")
            continue
        # Asked, not answered: nothing to publish. The phone replies with upserts that flow through _ingest_new
        # like any other message, so the thread fills itself on the next tick.
        logger.info(f"WhatsApp: pedidos {ack.get('requested')} mensajes anteriores de {chat_id}")
