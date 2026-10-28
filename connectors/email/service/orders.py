"""The operator's orders on his mail: mark read / unread, reply, write first, archive, trash. Each drain takes its
queue once from the inbox the facade holds and reports a failure to the card and the voice; nothing is retried in silence."""
import asyncio

from loguru import logger

from connectors.email import config
from connectors.messaging import ingest, store


def _tell_the_voice(text: str) -> None:
    try:
        from voice import brain_notes
        brain_notes.push(text)
    except Exception:
        pass


async def _drain_reads(mb) -> None:
    v2 = ingest.v2_enabled()
    keys = (_svc._mark_inbox.drain() if _svc._mark_inbox else []) if v2 else store.take_pending_read(_svc.PLATFORM)
    if not keys:
        return
    uids = [k.get("messageId") for k in keys if k.get("messageId")]     # email messageId = IMAP UID
    ok = await asyncio.to_thread(mb.mark_seen, uids)
    if not ok:
        logger.warning("Email mark-read falló (reintento luego)")
        if v2:
            for k in keys:
                ingest.publish_mark_read(k)
        else:
            store.requeue_pending_read(keys)


async def _drain_unreads(mb) -> None:
    """Put mails back to UNREAD in the real mailbox (msg.mark_unread). A failure re-queues, like mark-read."""
    if _svc._unread_inbox is None:
        return
    keys = _svc._unread_inbox.drain()
    if not keys:
        return
    uids = [k.get("messageId") for k in keys if k.get("messageId")]
    ok = await asyncio.to_thread(mb.mark_unseen, uids)
    if not ok:
        logger.warning("Email mark-unread falló (reintento luego)")
        for k in keys:
            ingest.publish_mark_unread(k)


async def _drain_replies(mb) -> None:
    """Drain pending replies (V2-051): send by SMTP with threading. v2 path only (widget owner enqueues in
    pending_reply → publishes msg.reply to the bus). Marks the original read after replying."""
    if not ingest.v2_enabled() or _svc._reply_inbox is None:
        return
    for r in _svc._reply_inbox.drain():
        to = (r.get("to") or r.get("chatId") or "").strip()
        text = r.get("text") or ""
        # V2-611 — the signature is appended EXACTLY ONCE, HERE, at the one place a real SMTP send happens.
        # It can never double up with Gmail's own: that auto-append is a client-side feature of Gmail's web
        # compose UI, and we never touch it — this is a raw SMTP send, the same mechanism a mail client uses
        # to talk to the SERVER, not to Gmail's own interface. The widget that queued `r` never saw the
        # signature and never will (V2-557: widget.js touches no network, and a data-op is not where account
        # content belongs) — it is connector state, read fresh so an edit applies to the very next send.
        lines = config.signature_lines()
        if lines:
            text = text.rstrip("\n") + "\n\n-- \n" + "\n".join(lines)   # RFC 3676 delimiter: clients that
                                                                          # trim signatures on reply look for it
        subject = r.get("subject") or ""
        in_reply_to = r.get("msgid") or ""
        # V2-680 — reply-ALL travels as a list of addresses, decided in the widget and resolved from the
        # ORIGINAL message's own recipients. An empty list is a plain reply, which is every other caller.
        cc = [str(a) for a in (r.get("cc") or []) if str(a).strip()]
        files = store.sendable(r.get("attachments") or [])
        # Files only when there are any: a plain reply calls exactly as it always did.
        extra = {"attachments": files} if files else {}
        ok, info = await asyncio.to_thread(mb.send_reply, to, subject, text, in_reply_to, cc, **extra)
        if ok:
            logger.info(f"Email: respuesta enviada a {to}")
            # V2-546 — record it in the conversation. Unlike WhatsApp and Telegram, sent mail does not come
            # back through the INBOX (it goes to the Sent folder), so nothing would ever echo it: without this
            # the operator's own reply would be the one message missing from the thread.
            import time as _t
            ingest.publish_msg_out(_svc.PLATFORM, {
                "chatId": to, "messageId": f"sent:{_t.time():.0f}:{(in_reply_to or to)[:60]}",
                "ref": r.get("ref") or "",       # V2-819: the card that sent it hears it left
                "from": "", "body": text, "timestamp": _t.time()})
            _tell_the_voice(f"[SISTEMA] Email enviado a {to}. Confírmaselo al operador de forma natural.")
            uid = r.get("messageId")
            if uid:
                await asyncio.to_thread(mb.mark_seen, [uid])
        else:
            logger.warning(f"Email: fallo al enviar a {to}: {info}")
            ingest.publish_send_failed({**r, "platform": _svc.PLATFORM}, str(info))   # V2-819: and the card hears why
            _tell_the_voice(f"[SISTEMA] No se pudo enviar el email a {to} ({info}). Avísale al operador.")


async def _drain_sends(mb) -> None:
    """Drain orders that OPEN a conversation (V2-683): a first message to somebody, by SMTP.

    The send itself is `send_reply` with no `in_reply_to` — which is what it already does for a mail that has
    no thread to continue, so nothing new reaches the network here. The differences with a reply are the two
    that matter: the subject is the errand's own (there is no «Re:» to inherit), and the echo carries the
    order's `ref`, which is what lets whatever asked for this bind the conversation it just created."""
    if not ingest.v2_enabled() or _svc._send_inbox is None:
        return
    for r in _svc._send_inbox.drain():
        to = str(r.get("to") or r.get("chatId") or "").strip()
        text = r.get("text") or ""
        if not to or not text.strip():
            continue
        lines = config.signature_lines()
        if lines:
            text = text.rstrip("\n") + "\n\n-- \n" + "\n".join(lines)
        subject = str(r.get("subject") or "").strip() or "Hola"
        # V2-718 — the same queue carries an INVITATION when the order brings one: the difference is not the
        # recipient or the words, it is that the message has a calendar object inside it that the other
        # person's client can accept. Anything without `ics` takes the byte-identical path it always took.
        ics = str(r.get("ics") or "")
        atts = store.sendable(r.get("attachments") or [])
        if ics.strip():
            ok, info = await asyncio.to_thread(mb.send_invitation, to, subject, text, ics,
                                               str(r.get("ics_method") or "REQUEST"), None)
        else:
            # a FIRST message is a new mail, never a «Re:» (it went out as «Re: Hola» — 2026-09-28); files, if the
            # order carries them, ride with it
            ok, info = await asyncio.to_thread(mb.send_message, to, subject, text, atts)
        if ok:
            logger.info(f"Email: mensaje enviado a {to} (ref {r.get('ref')})")
            import time as _t
            # The address IS the conversation's id for email (the thread store keys on it), so unlike
            # Telegram and WhatsApp there is nothing to resolve — the echo still carries `ref` so every
            # platform binds the same way.
            ingest.publish_msg_out(_svc.PLATFORM, {
                "chatId": to, "messageId": f"sent:{_t.time():.0f}:{to[:60]}", "ref": r.get("ref"),
                "from": "", "body": text, "timestamp": _t.time(),
                "chatName": r.get("name") or to})
        else:
            logger.warning(f"Email: fallo al escribir a {to}: {info}")
            ingest.publish_send_failed(r, str(info))
            _tell_the_voice(f"[SISTEMA] No se pudo escribir a {r.get('name') or to} por correo ({info}). "
                            f"Avísale al operador; no lo he reintentado.")


async def _drain_disposals(mb) -> None:
    """Drain archive/delete orders (V2-543) and execute them in the REAL mailbox. The widget already removed
    the item and (for trash) the confirm gate already asked; a failure is TOLD, never silently retried — same
    policy as replies."""
    if not ingest.v2_enabled():
        return
    for inbox, verb in ((_svc._archive_inbox, "archive"), (_svc._trash_inbox, "trash")):
        if inbox is None:
            continue
        keys = inbox.drain()
        if not keys:
            continue
        uids = [k.get("messageId") for k in keys if k.get("messageId")]
        fn = mb.archive if verb == "archive" else mb.trash
        ok, why = await asyncio.to_thread(fn, uids)
        label = "archivar" if verb == "archive" else "borrar"
        if ok:
            logger.info(f"Email: {label} {len(uids)} → {why}")
        else:
            logger.warning(f"Email: fallo al {label}: {why}")
            _tell_the_voice(f"[SISTEMA] No se pudo {label} el correo en el buzón real ({why}). "
                            "Avísale al operador.")


from connectors.email import service as _svc  # noqa: E402 — the facade: this module reads its inboxes back
