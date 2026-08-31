#
# service.py — Email connector ENGINE integrated into zaelar (V2-051). Runs IN PROCESS in the server lifespan
# (UI-gated), as an asyncio task. Email is the CLEANEST of the three connectors: pure stdlib (imaplib/smtplib), NO
# Node bridge (WhatsApp), and no third-party lib (Telethon). Network logic lives in mailbox.py and ALWAYS runs in
# asyncio.to_thread (IMAP/SMTP block) → never clogs the server event loop.
#
# Flow (stateless v2 production path, BRAIN=nucleo): IMAP/SMTP login → poll INBOX (BODY.PEEK, does not mark read)
# → publish NEW emails to the messaging widget (connector.msg), which triages/saves/notifies. Drains:
#   · msg.mark_read (MarkReadInbox) → mailbox.mark_seen (marks \Seen in IMAP).
#   · msg.reply      (ReplyInbox)   → mailbox.send_reply (SMTP with In-Reply-To/References threading).
# Direct duo/hermes path (fallback): triages with the shared classifier and writes the store like WhatsApp/Telegram.
#
import asyncio

from loguru import logger

from connectors.email import config
from connectors.messaging import ingest, notify, store, triage

PLATFORM = "email"

_task: asyncio.Task | None = None
_seen: set[str] = set()          # already-seen IMAP UIDs (seeded on connect → only triage NEW email)
_published: set[str] = set()     # v2: UIDs already published to the bus (dedup before triage in the widget)
_shown: set[str] = set()         # direct path: messageIds already surfaced
_mark_inbox = None               # v2: msg.mark_read subscription (created in THIS loop)
_reply_inbox = None              # v2: msg.reply subscription (created in THIS loop)


def enabled() -> bool:
    return config.enabled()


def _set_status(status: str, qr=None, detail=None) -> None:
    try:
        if ingest.v2_enabled():
            ingest.publish_status(PLATFORM, status, qr, detail)
        else:
            store.set_platform_status(PLATFORM, status, qr, detail)
    except Exception as e:
        logger.debug(f"Email set_status: {e}")


def _friendly_error(why: str) -> str:
    """Translate the technical reason for an IMAP/SMTP failure into something ACTIONABLE for the user (no jargon)."""
    w = (why or "").lower()
    if "imap" in w and ("auth" in w or "login" in w or "invalid credentials" in w or "[alert]" in w):
        return ("No pude iniciar sesión. En Gmail/Outlook usa una CONTRASEÑA DE APLICACIÓN (no tu contraseña "
                "normal) con la verificación en 2 pasos activada, y comprueba la dirección.")
    if "smtp" in w and ("auth" in w or "5.7" in w or "login" in w):
        return ("El correo se lee pero no pude autenticar el ENVÍO (SMTP). Suele ser la misma contraseña de "
                "aplicación; revisa que el envío por SMTP esté permitido en tu cuenta.")
    if "nodename" in w or "not known" in w or "getaddrinfo" in w or "resolve" in w:
        return "No encuentro el servidor de correo. Revisa el proveedor o los servidores IMAP/SMTP."
    if "timed out" in w or "timeout" in w:
        return "El servidor de correo no respondió a tiempo. Revisa tu conexión y vuelve a intentarlo."
    if "certificate" in w or "ssl" in w:
        return "Error de seguridad (SSL) al conectar con el servidor de correo. Revisa el host/puerto."
    return f"No pude conectar con tu correo: {why}"


async def _ingest_new(mb) -> None:
    """Read INBOX in a thread, publish/triage new emails. Updates `_seen`/`_published`."""
    msgs = await asyncio.to_thread(mb.fetch_new, _seen)
    if not msgs:
        return
    for m in msgs:
        _seen.add(m.get("messageId"))
    if ingest.v2_enabled():
        for m in msgs:
            mid = m.get("messageId")
            if mid and mid not in _published:
                _published.add(mid)
                ingest.publish_msg(PLATFORM, m)
        return
    # Direct path (duo/hermes): triage + store + notification, like WhatsApp/Telegram.
    verdicts = await triage.classify(msgs, config.operator_name() or None)
    surfaced = notify.surface(verdicts, _shown)
    if not surfaced:
        return
    for v in surfaced:
        _shown.add(v.get("messageId"))
        v["from"] = v.get("senderName") or v.get("chatId") or "?"
        v["group"] = None
    store.upsert_items(PLATFORM, surfaced)
    logger.info(f"Email: +{len(surfaced)} para ti")
    await notify.announce("Email", surfaced)


async def _drain_reads(mb) -> None:
    v2 = ingest.v2_enabled()
    keys = (_mark_inbox.drain() if _mark_inbox else []) if v2 else store.take_pending_read(PLATFORM)
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


async def _drain_replies(mb) -> None:
    """Drain pending replies (V2-051): send by SMTP with threading. v2 path only (widget owner enqueues in
    pending_reply → publishes msg.reply to the bus). Marks the original read after replying."""
    if not ingest.v2_enabled() or _reply_inbox is None:
        return
    for r in _reply_inbox.drain():
        to = (r.get("to") or r.get("chatId") or "").strip()
        text = r.get("text") or ""
        subject = r.get("subject") or ""
        in_reply_to = r.get("msgid") or ""
        ok, info = await asyncio.to_thread(mb.send_reply, to, subject, text, in_reply_to)
        if ok:
            logger.info(f"Email: respuesta enviada a {to}")
            try:
                from voice import brain_notes
                brain_notes.push(f"[SISTEMA] Email enviado a {to}. Confírmaselo al operador de forma natural.")
            except Exception:
                pass
            uid = r.get("messageId")
            if uid:
                await asyncio.to_thread(mb.mark_seen, [uid])
        else:
            logger.warning(f"Email: fallo al enviar a {to}: {info}")
            try:
                from voice import brain_notes
                brain_notes.push(f"[SISTEMA] No se pudo enviar el email a {to} ({info}). Avísale al operador.")
            except Exception:
                pass


async def _loop() -> None:
    global _mark_inbox, _reply_inbox
    _set_status("starting", None, "Conectando con el servidor de correo…")
    mb = config.mailbox()
    if mb is None:
        _set_status("no_creds", None, "Faltan datos: dirección de correo y contraseña de aplicación.")
        logger.warning("Email: faltan credenciales (dirección/app-password/IMAP/SMTP) — el widget lo indicará")
        return
    _set_status("starting", None, f"Verificando IMAP y SMTP de {config.imap_host()}… (puede tardar unos segundos)")
    ok, why = await asyncio.to_thread(mb.test_connection)
    if not ok:
        logger.error(f"Email: no pude conectar: {why}")
        _set_status("error", None, _friendly_error(why))     # 'error' (not 'no_creds'): configured but failed → card with reason + retry
        return
    _seen.update(await asyncio.to_thread(mb.all_uids))     # only triage email that arrives AFTER connecting
    if ingest.v2_enabled():
        if _mark_inbox is None:
            _mark_inbox = ingest.MarkReadInbox(PLATFORM)
        if _reply_inbox is None:
            _reply_inbox = ingest.ReplyInbox(PLATFORM)
    _set_status("connected", None, f"Conectado como {config.address()}.")
    logger.info(f"Email conectado ({config.address()}) — escuchando tu buzón")
    while True:
        try:
            await _ingest_new(mb)
        except Exception as e:
            logger.debug(f"Email ingest tick: {e}")
        try:
            await _drain_reads(mb)
        except Exception as e:
            logger.debug(f"Email reads tick: {e}")
        try:
            await _drain_replies(mb)
        except Exception as e:
            logger.debug(f"Email reply tick: {e}")
        await asyncio.sleep(config.poll_interval())


def start() -> None:
    """Start the engine as a background task (server lifespan, if the connector is enabled from the UI)."""
    global _task
    if not enabled():
        _set_status("off", None)
        logger.info("Email: desactivado")
        return
    if not config.has_credentials():
        _set_status("no_creds", None, "Faltan datos: dirección de correo y contraseña de aplicación.")
        logger.warning("Email: activado pero faltan credenciales — el widget mostrará el formulario")
        return
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info("Email: motor arrancado")


async def stop() -> None:
    global _task, _mark_inbox, _reply_inbox
    if _task:
        _task.cancel()
        _task = None
    for inbox in (_mark_inbox, _reply_inbox):
        try:
            if inbox is not None:
                inbox.close()
        except Exception:
            pass
    _mark_inbox = _reply_inbox = None
    _seen.clear()
    _published.clear()
    _shown.clear()
