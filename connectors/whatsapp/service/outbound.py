#
# outbound.py — what zaelar SENDS through the bridge: one message as the app sends it, a dictated reply and its
# echo, the JID a phone becomes, and a first message to somebody who has not written.
#
from loguru import logger

from connectors.messaging import ingest, store
from connectors.whatsapp import client
from connectors.whatsapp import service as _svc

PLATFORM = _svc.PLATFORM


async def _send(chat_id: str, text: str, files: list[str], reply_to: str | None = None) -> dict:
    """One message as the native app sends it: the files, the text as the FIRST file's caption when that file
    can carry one (a voice note cannot), otherwise the text on its own. Returns the last send's answer."""
    files = store.sendable(files)
    if not files:
        return await client.send_message(chat_id, text, reply_to=reply_to) or {}
    res: dict = {}
    caption_used = False
    for i, path in enumerate(files):
        cap = text if (i == 0 and text and store.kind_of(path) not in ("ptt", "audio")) else ""
        caption_used = caption_used or bool(cap)
        res = await client.send_media(chat_id, path, caption=cap) or {}
    if text and not caption_used:
        res = await client.send_message(chat_id, text, reply_to=reply_to) or res
    return res


async def _drain_replies() -> None:
    """Drain dictated replies (V2-521 — the email connector had this since V2-051; WhatsApp only ever read).
    The widget's reply action already enqueued mark-read for the original, so this only SENDS. A failure is
    TOLD to the operator through brain_notes and not requeued: a bad send retried forever is worse than one
    honest "I couldn't send it."""
    if not ingest.v2_enabled() or _svc._reply_inbox is None:
        return
    for r in _svc._reply_inbox.drain():
        chat_id = str(r.get("chatId") or r.get("to") or "").strip()
        text = (r.get("text") or "").strip()
        files = r.get("attachments") or []
        if not chat_id or not (text or files):
            continue
        try:
            res = await _svc._send(chat_id, text, files, reply_to=r.get("messageId") or None)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"WhatsApp: fallo al enviar a {chat_id}: {e}")
            # V2-819 — and the card that sent it hears it too: its row keeps his text and says why.
            ingest.publish_send_failed({**r, "platform": PLATFORM}, str(e))
            _svc._note(f"[SISTEMA] No se pudo enviar el WhatsApp a {r.get('to') or chat_id} ({e}). Avísale al operador.")
            continue
        logger.info(f"WhatsApp: respuesta enviada a {chat_id}")
        _svc._note(f"[SISTEMA] WhatsApp enviado a {r.get('to') or chat_id}. Confírmaselo al operador de forma natural.")
        _svc._echo_sent(r, chat_id, text, files, res)


def _echo_sent(r: dict, chat_id: str, text: str, files: list, res: dict | None) -> None:
    """V2-819 — a reply that LEFT joins its conversation now, under the id WhatsApp gave it (the phone's own echo
    of the same message then lands on the same row), and carries the order's `ref` so the card that sent it
    knows. Outside the send's try on purpose: failing to RECORD a message is not failing to SEND it."""
    try:
        import time as _t
        mid = (res or {}).get("messageId") or f"sent:{_t.time():.0f}"
        _svc._published.add(mid)
        ingest.publish_msg_out(PLATFORM, {
            "chatId": chat_id, "messageId": mid, "ref": r.get("ref") or "", "from": "", "body": text,
            "timestamp": _t.time(),
            **({"media": store.media_refs(store.sendable(files)),
                "mediaType": store.kind_of(files[0])} if files else {})})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"WhatsApp: enviado, pero no pude registrar la conversación: {e}")


def _jid(handle: str) -> str:
    """The conversation id WhatsApp addresses a person by, from whatever we hold. A JID is already one; a
    phone becomes `<digits>@s.whatsapp.net`, which is exactly what the bridge's own chat ids look like — so a
    conversation opened this way is keyed the same as one that arrived on its own, and the thread does not
    split in two. Punctuation and spaces are dropped because a stored number is written for a human."""
    h = str(handle or "").strip()
    if "@" in h:
        return h
    digits = "".join(ch for ch in h if ch.isdigit())
    return f"{digits}@s.whatsapp.net" if digits else ""


async def _drain_sends() -> None:
    """Drain orders that OPEN a conversation (V2-683): a first message to somebody who has not written.

    WhatsApp has no «resolve this person» step — a number IS the address — so the only translation is the JID
    above. What the bridge cannot tell us is whether that number has WhatsApp at all: it answers with an
    error, and that error is reported once and never retried, which is the honest half of the asymmetry
    `widgets/directory.py` documents (a phone is offered for WhatsApp only when the operator NAMED it)."""
    if not ingest.v2_enabled() or _svc._send_inbox is None:
        return
    for r in _svc._send_inbox.drain():
        chat_id = str(r.get("chatId") or "").strip() or _jid(r.get("to"))
        text = (r.get("text") or "").strip()
        files = r.get("attachments") or []
        if not chat_id or not (text or files):
            continue
        try:
            res = await _svc._send(chat_id, text, files)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"WhatsApp: fallo al escribir a {chat_id}: {e}")
            ingest.publish_send_failed(r, str(e))
            _svc._note(f"[SISTEMA] No pude escribir a {r.get('name') or chat_id} por WhatsApp ({e}). Puede que ese "
                       f"número no tenga WhatsApp. Díselo al operador; no lo he reintentado.")
            continue
        # SENT — the echo sits outside the try on purpose (see the Telegram drain): a failure to RECORD the
        # message must never be reported as a failure to SEND it.
        logger.info(f"WhatsApp: mensaje enviado a {chat_id} (ref {r.get('ref')})")
        try:
            import time as _t
            ingest.publish_msg_out(PLATFORM, {
                "chatId": chat_id, "messageId": (res or {}).get("messageId") or f"sent:{_t.time():.0f}",
                "ref": r.get("ref"), "from": "", "body": text, "timestamp": _t.time(),
                "contactId": r.get("contactId") or "",
                "chatName": r.get("name") or "",
                **({"media": store.media_refs(store.sendable(files)),
                    "mediaType": store.kind_of(files[0])} if files else {})})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"WhatsApp: enviado, pero no pude registrar la conversación: {e}")
