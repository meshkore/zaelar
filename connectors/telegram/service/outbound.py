#
# outbound.py — what zaelar SENDS: a dictated reply, and a first message to somebody who has not written. The send
# itself is `account_ops._send`; inboxes and the collaborators a test replaces are read from the facade at call time.
#
from loguru import logger

from connectors.messaging import ingest, store
from connectors.telegram import service as _svc


async def _drain_replies() -> None:
    """Drain dictated replies (V2-521 — same seam the email connector has had since V2-051; Telegram only
    ever read). The widget already enqueued mark-read for the original, so this only SENDS. A failure is
    TOLD to the operator and not requeued — one honest "no pude enviarlo" beats a send retried forever."""
    if not ingest.v2_enabled() or _svc._reply_inbox is None:
        return
    for r in _svc._reply_inbox.drain():
        text = (r.get("text") or "").strip()
        try:
            chat_id = int(r.get("chatId"))
        except (TypeError, ValueError):
            continue
        files = r.get("attachments") or []
        if not (text or files):
            continue
        reply_to = _svc._tg_msg_id(r.get("messageId"))   # composite-aware: replies land THREADED, not loose
        try:
            # ⚠️ PARSE_MODE=NONE, and it is not a detail (V2-693). Telethon's default is MARKDOWN, so it
            # PARSES what we send: it consumes `_`, `*` and `` ` `` as formatting, and it hands Telegram a
            # message with its own entity list — and a message that arrives carrying entities is one
            # Telegram does NOT run its URL auto-detection over. The operator measured it on the Meet
            # link: «sale el embedding conforme ha reconocido el link pero no es clicable». Our text is
            # prose a model wrote for a human, never markup; an underscore in it is an underscore.
            sent = await _svc._send(chat_id, text, files, reply_to=reply_to)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Telegram: fallo al enviar a {chat_id}: {e}")
            # V2-819 — the card that sent it hears it too: its row keeps his text and says why.
            ingest.publish_send_failed({**r, "platform": "telegram"}, str(e))
            _svc._note(f"[SISTEMA] No se pudo enviar el Telegram a {r.get('to') or chat_id} ({e}). Avísale al operador.")
            continue
        logger.info(f"Telegram: respuesta enviada a {chat_id}")
        _svc._note(f"[SISTEMA] Telegram enviado a {r.get('to') or chat_id}. Confírmaselo al operador de forma natural.")
        # V2-819 — and the card that sent it hears it LEFT: the echo carries the order's `ref`, under the same id
        # the account's own outgoing event gives it, so the two land on one row. Outside the try: failing to
        # record a message is not failing to send it.
        try:
            ingest.publish_msg_out("telegram", {
                "chatId": chat_id, "messageId": f"{chat_id}:{getattr(sent, 'id', 0)}", "ref": r.get("ref") or "",
                "from": "", "body": text, "timestamp": _sent_ts(sent),
                **({"media": store.media_refs(store.sendable(files)),
                    "mediaType": store.kind_of(files[0])} if files else {})})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Telegram: enviado, pero no pude registrar la conversación: {e}")


async def _drain_sends() -> None:
    """Drain orders that OPEN a conversation (V2-683): a first message to somebody who has not written.

    The one real difference with a reply: a reply already holds the `chatId`, and here we hold a HANDLE — a
    @username or a phone — that Telegram still has to resolve into a person. Telethon does that itself when
    `send_message` is given the string, so nothing is re-implemented; what matters is what happens when it
    CANNOT: a phone that is not in the account's contacts, or a username that does not exist, raises, and the
    honest answer is to say so once and stop. Never a retry — a message retried at somebody is worse than a
    message not sent."""
    if not ingest.v2_enabled() or _svc._send_inbox is None:
        return
    for r in _svc._send_inbox.drain():
        to = str(r.get("to") or "").strip()
        text = (r.get("text") or "").strip()
        files = r.get("attachments") or []
        if not to or not (text or files):
            continue
        try:
            # An id we already hold travels as an int (that IS the conversation); a handle stays a string for
            # Telethon to resolve. Sending to the wrong peer because «600111222» was read as a user id is
            # exactly the mistake this door cannot make.
            peer = int(r["chatId"]) if str(r.get("chatId") or "").strip().lstrip("-").isdigit() else to
            sent = await _svc._send(peer, text, files)   # parse_mode=None: see the reply drain
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Telegram: fallo al escribir a {to}: {e}")
            ingest.publish_send_failed(r, str(e))
            _svc._note(f"[SISTEMA] No pude escribir a {r.get('name') or to} por Telegram ({e}). Puede que ese "
                       f"usuario no exista o que ese teléfono no esté en sus contactos de Telegram. Díselo al "
                       f"operador; no lo he reintentado.")
            continue
        # SENT. Everything below is bookkeeping, and it lives outside the try for a reason a test caught
        # before this shipped: with the echo inside it, a NameError after a successful send was reported to
        # the operator as «no pude escribir» over a message that had already reached the person.
        logger.info(f"Telegram: mensaje enviado a {to} (ref {r.get('ref')})")
        try:
            chat_id = getattr(sent, "chat_id", None)
            if chat_id is None:
                chat_id = peer if isinstance(peer, int) else None
            if chat_id is not None:
                # The echo carries the id Telegram RESOLVED, which is the only place it exists: the caller
                # asked by handle and could not have known it.
                ingest.publish_msg_out("telegram", {
                    "chatId": chat_id, "messageId": f"{chat_id}:{getattr(sent, 'id', 0)}",
                    "ref": r.get("ref"), "from": "", "body": text,
                    "contactId": r.get("contactId") or "",
                    "timestamp": _sent_ts(sent), "chatName": r.get("name") or "",
                    **({"media": store.media_refs(store.sendable(files)),
                        "mediaType": store.kind_of(files[0])} if files else {})})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Telegram: enviado, pero no pude registrar la conversación: {e}")


def _sent_ts(sent) -> float:
    import time as _t
    try:
        return sent.date.timestamp()
    except Exception:
        return _t.time()
