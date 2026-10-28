"""The on-demand reads the operator waits on: scrollback, a pull of recent activity, a folder page or one message."""
import asyncio

from loguru import logger

from connectors.messaging import ingest, store

from .inbound import _media_dir


async def _drain_history(mb) -> None:
    """Serve "load previous" (V2-546). IMAP holds the whole mailbox on the server, so this is exact: earlier
    mail from the same correspondent, and we know when we have reached the first one."""
    if _svc._history_inbox is None:
        return
    for order in _svc._history_inbox.drain():
        chat_id, before = order.get("chatId"), order.get("beforeId")
        if not chat_id or not before:
            ingest.publish_history(_svc.PLATFORM, chat_id, [],
                                   error="no sé por dónde empieza lo que tengo de ese remitente")
            continue
        try:
            limit = max(1, min(100, int(order.get("limit") or 30)))
        except (TypeError, ValueError):
            limit = 30
        msgs, complete = await asyncio.to_thread(mb.fetch_older, str(chat_id), str(before), limit, _media_dir())
        rows = []
        for m in msgs:
            subject = (m.get("subject") or "").strip()
            body = m.get("body") or ""
            rows.append({
                "messageId": m.get("messageId"), "dir": "in",
                "from": m.get("senderName") or m.get("chatId") or "?",
                # A mail without its subject is half a mail; the widget's own splitBody renders the first line
                # as a title, so joining them here needs no special case downstream.
                "body": f"{subject}\n{body}" if subject else body,
                "ts": m.get("timestamp") or 0, "read": True,
                # …and the mail's own fields, which the thread keeps (V2-680) and `forward` names its subject from:
                # a mail brought back without them went out to Quinn as «Fwd» (demo pass 31, E3)
                **{k: m[k] for k in ("subject", "senderId", "recipients") if m.get(k)},
                # …with its files, in the shape ingestion gives them: a mail brought back to be FORWARDED must carry
                # what it carried (full28 E3: the Inworld invoice)
                **({"media": store._media_entries(m)} if m.get("mediaUrls") else {}),
            })
        ingest.publish_history(_svc.PLATFORM, chat_id, rows, complete=complete)
        logger.info(f"Email: +{len(rows)} mensajes anteriores de {chat_id}")


async def _drain_fetch(mb) -> None:
    """Serve a platform-wide pull (V2-624 — «chupar más mensajes», «la actividad de las últimas 72 horas»).
    IMAP searches the whole mailbox by date, so this is exact to the cutoff DAY (the search granularity) and
    trimmed to the hour here. Everything lands in the CONVERSATIONS as read scrollback via the same
    connector.history seam "load previous" uses — never in triage: pulling the past must not interrupt.
    `parse_message`'s automated-sender filter applies on purpose: this widget is a triage surface, and the
    newsletters it never shows live are not «conversations» when pulled either."""
    if _svc._fetch_inbox is None:
        return
    for order in _svc._fetch_inbox.drain():
        try:
            hours = max(1.0, float(order.get("since_hours") or 72))
        except (TypeError, ValueError):
            hours = 72.0
        msgs = await asyncio.to_thread(mb.search_since, hours, 100, _media_dir())
        import time as _t
        cutoff = _t.time() - hours * 3600
        by_chat: dict[str, list[dict]] = {}
        for m in msgs:
            ts = float(m.get("timestamp") or 0)
            if ts and ts < cutoff:
                continue                     # SINCE over-fetches to the start of the cutoff day
            by_chat.setdefault(str(m.get("chatId") or "?"), []).append(m)
        total = 0
        for chat_id, rows_in in by_chat.items():
            rows = []
            for m in rows_in:
                subject = (m.get("subject") or "").strip()
                body = m.get("body") or ""
                rows.append({"messageId": m.get("messageId"), "dir": "in",
                             "from": m.get("senderName") or chat_id,
                             "body": f"{subject}\n{body}" if subject and not body.startswith("[Asunto:") else body,
                             "ts": m.get("timestamp") or 0, "read": True})
            name = next((m.get("senderName") for m in rows_in if m.get("senderName")), chat_id)
            ingest.publish_history(_svc.PLATFORM, chat_id, rows, name=name, is_group=False)
            total += len(rows)
        logger.info(f"Email: fetch de {hours:.0f}h → {total} mensajes en {len(by_chat)} conversación(es)")
        try:
            from voice import brain_notes
            if total:
                brain_notes.push(f"[SISTEMA] Traída de Email hecha: {total} mensaje(s) de las últimas "
                                 f"{hours:.0f} h en {len(by_chat)} conversación(es), ya en el widget de "
                                 f"mensajería. Cuéntaselo al operador.")
            else:
                brain_notes.push(f"[SISTEMA] Traída de Email hecha: no hay correos (no automáticos) en las "
                                 f"últimas {hours:.0f} h. Díselo al operador tal cual.")
        except Exception:
            pass


async def _drain_mailbox(mb) -> None:
    """Serve the card's mail-client orders: one page of a folder, or one message read whole. The answer goes back
    on `connector.mailbox` — including a failure, so the card can say why a folder is empty."""
    if _svc._mailbox_inbox is None:
        return
    from connectors.email import folders as _folders
    for order in _svc._mailbox_inbox.drain():
        folder = str(order.get("folder") or "INBOX")
        if order.get("open"):
            msg = await asyncio.to_thread(_folders.read_one, mb, folder, str(order["open"]), _media_dir())
            ingest.publish_mailbox(_svc.PLATFORM, {"folder": folder, "open": msg})
            continue
        try:
            limit = max(1, min(100, int(order.get("limit") or 30)))
        except (TypeError, ValueError):
            limit = 30
        extra = {"category": order["category"], "routes": order.get("routes") or []} if order.get("category") else {}
        page = await asyncio.to_thread(_folders.list_page, mb, folder, order.get("before"), limit, **extra)
        ingest.publish_mailbox(_svc.PLATFORM, {"folder": folder, "before": order.get("before"), **page})


from connectors.email import service as _svc  # noqa: E402 — the facade: this module reads its queues back
