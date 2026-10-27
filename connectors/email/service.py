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

#: How many of the UNREAD backlog are handed to the widget on connect. A triage surface is a list somebody
#: READS; the rest of the mailbox stays in the mailbox, and the total travels as a fact instead (V2-606).
BACKFILL = 30

_unread_total: int = -1          # UNSEEN in INBOX at the last connect. -1 = not measured (never guessed as 0).


def _set_unread_total(n: int) -> None:
    global _unread_total
    _unread_total = int(n)


def seed_from_mailbox(mb) -> int:
    """Decide what the widget may EVER see, and record how much mail is really waiting. Returns the unread total.

    V2-606. This used to be `_seen.update(mb.all_uids())` inline in `_loop`, under the comment «only triage email
    that arrives AFTER connecting» — so the widget could only ever show mail that arrived after the connector
    started, and `_seen` lives in memory, so every restart moved that line forward again. Measured on the
    operator's real mailbox: **1110 in INBOX, 1088 UNSEEN**, all 1110 declared already-seen on connect. The
    connector authenticated, reported «Conectado» and showed him nothing, forever.

    The line is drawn where the operator already draws it: mail he has READ is dealt with and does not come back;
    mail he has NOT read is the thing he is asking to see.

    A triage surface is not a mailbox, so only the most recent `BACKFILL` unread are handed over — and that is
    exactly why the TOTAL is recorded. Silently hiding the other thousand is the failure being replaced; the
    count is what lets the agent say «tienes 1088 sin leer» instead of «no tienes mensajes nuevos sin leer»,
    which is what it said, over a full inbox (session `43b7bf79`).

    A FUNCTION and not four lines inside `_loop` because `_loop` connects to a real server: with the decision in
    there, a test can only re-implement it, and a re-implementation proves the test works, not the product. Three
    disarms came back green before this was extracted.
    """
    read, unread = mb.inbox_split()
    _seen.update(read)
    if len(unread) > BACKFILL:
        _seen.update(unread[:-BACKFILL])
    _set_unread_total(len(unread))
    logger.info(f"Email: {len(unread)} sin leer en INBOX; entran los {min(len(unread), BACKFILL)} más recientes")
    return len(unread)


def unread_total() -> int:
    """UNSEEN messages in the operator's INBOX as of the last connect, or -1 if we have not measured it.

    -1 and 0 are DIFFERENT and the difference is the whole point: «no lo sé» must never render as «no tienes
    ninguno», which is the sentence the agent said over 1088 unread mails.
    """
    return _unread_total


async def reseed() -> int:
    """Forget this connector's own memory of what it already delivered — called when Reset blanks the widget's
    store, so mail this connector handed over once does not become invisible FOREVER.

    `_seen`/`_published` are populated once at connect (`seed_from_mailbox`) and again on every real delivery
    (`_ingest_new`), and are otherwise cleared ONLY by `stop()` (a full disconnect). Reset
    (`widgets/reset.py` → `widgets/mensajeria/data.py::blank()`) wipes the widget's `items` AND its durable
    `taken` ledger, but it is a WIDGET-side operation and never touches a connector's own process state — so a
    message this connector already delivered once stays in `_seen` forever, and `fetch_new(seen=_seen, ...)`
    (`mailbox.py:420`) skips it on every future poll. The widget forgot it; the connector still insists it was
    already handed over — genuinely unread mail vanishes from view until the engine restarts (which is the only
    thing that currently calls `stop()`).

    Measured live on the operator's engine: 1081 real unread in Gmail, zero reaching the widget, `taken` holding
    no `email:*` entry at all — exactly this. Releases only the most recent `BACKFILL` unread, the SAME shape
    `seed_from_mailbox` already produces on a fresh connect, so this cannot flood the widget with the whole
    backlog at once; the next poll tick's `_ingest_new` redelivers them normally, straight into the
    freshly-blanked store."""
    if not (_task and not _task.done()):
        return -1
    mb = config.mailbox()
    if mb is None:
        return -1
    ok, why = await asyncio.to_thread(mb.test_connection)
    if not ok:
        return -1
    read, unread = await asyncio.to_thread(mb.inbox_split)
    recent = set(unread[-BACKFILL:])
    _seen.difference_update(recent)
    _published.difference_update(recent)
    _set_unread_total(len(unread))
    return len(unread)
_shown: set[str] = set()         # direct path: messageIds already surfaced
_mark_inbox = None               # v2: msg.mark_read subscription (created in THIS loop)
_reply_inbox = None              # v2: msg.reply subscription (created in THIS loop)
_send_inbox = None               # V2-683: msg.send — writing to somebody who has not written
_unread_inbox = None             # msg.mark_unread — put a mail back to unread (the rehearsal rule)
_archive_inbox = None            # V2-543: msg.archive subscription
_trash_inbox = None              # V2-543: msg.trash subscription
_history_inbox = None            # V2-546: msg.history subscription ("load previous")
_fetch_inbox = None              # V2-624: msg.fetch subscription (platform-wide pull)
_mailbox_inbox = None            # msg.mailbox subscription (a folder page, or one message, for the card)


def _media_dir() -> str | None:
    """Where attachments land (V2-543): the messaging widget's own data dir — the one place its asset route
    serves. None on any failure → the mail still arrives, text-only, like before."""
    try:
        from widgets import store as wstore
        return wstore.data_dir("mensajeria")
    except Exception:
        return None


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


def _auth_failure_hint() -> str:
    """What to say when the server refuses the credentials (V2-559). The generic advice — «use an app password» —
    is useless to someone who already created one, and it is what the operator got after following the guide and
    pasting a LINK instead of the password. So the stored value is looked at first: when it CANNOT be an app
    password we say what was pasted, and only otherwise fall back to the per-provider causes."""
    try:
        from connectors.email import credentials as _creds
        pid = config.resolved_provider_id()
        why = _creds.diagnose(pid, config.address(), config.password())
        if why:
            return why
    except Exception:
        pid = ""
    tail = ("La contraseña es correcta pero el servidor la rechaza: revisa la dirección y que la contraseña de "
            "aplicación siga activa.")
    if pid == "gmail":
        domain = config.address().split("@")[-1].lower()
        own = domain and "gmail" not in domain and "googlemail" not in domain
        tail = ("Comprueba en Gmail que el acceso IMAP esté ACTIVADO (Configuración → Reenvío y correo POP/IMAP) "
                "y que la contraseña de aplicación siga activa.")
        if own:
            # A custom domain on Google Workspace: same servers, but two extra switches only an admin can flip.
            tail += (f" Tu dirección es de tu propio dominio ({domain}), así que puede ser Google Workspace: ahí "
                     "el administrador puede tener desactivadas las contraseñas de aplicación o el acceso IMAP.")
    return f"No pude iniciar sesión con esa contraseña. {tail}"


def _friendly_error(why: str) -> str:
    """Translate the technical reason for an IMAP/SMTP failure into something ACTIONABLE for the user (no jargon)."""
    w = (why or "").lower()
    if "imap" in w and ("auth" in w or "login" in w or "invalid credentials" in w or "[alert]" in w):
        return _auth_failure_hint()
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
    msgs = await asyncio.to_thread(mb.fetch_new, _seen, _media_dir())
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
    # V2-607 — the direct path splits the same two questions as the v2 owner: what is NEW goes into his
    # inbox, and only then is a notice considered. Before, `notify.surface` decided BOTH, so flipping the
    # notification default to silence would have left this path storing nothing at all — a connected
    # channel showing an empty list, which is the exact failure V2-606 had just fixed.
    fresh = store.new_among(store.load(), PLATFORM, verdicts)
    if not fresh:
        return
    for v in fresh:
        _shown.add(v.get("messageId"))
        v["from"] = v.get("senderName") or v.get("chatId") or "?"
        v["group"] = None
    store.upsert_items(PLATFORM, fresh)
    notice = notify.deserving(fresh)
    logger.info(f"Email: +{len(fresh)} ({len(notice)} avisan)")
    if notice:
        await notify.announce("Email", notice)


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


async def _drain_unreads(mb) -> None:
    """Put mails back to UNREAD in the real mailbox (msg.mark_unread). A failure re-queues, like mark-read."""
    if _unread_inbox is None:
        return
    keys = _unread_inbox.drain()
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
    if not ingest.v2_enabled() or _reply_inbox is None:
        return
    for r in _reply_inbox.drain():
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
            ingest.publish_msg_out(PLATFORM, {
                "chatId": to, "messageId": f"sent:{_t.time():.0f}:{(in_reply_to or to)[:60]}",
                "ref": r.get("ref") or "",       # V2-819: the card that sent it hears it left
                "from": "", "body": text, "timestamp": _t.time()})
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
            ingest.publish_send_failed({**r, "platform": PLATFORM}, str(info))   # V2-819: and the card hears why
            try:
                from voice import brain_notes
                brain_notes.push(f"[SISTEMA] No se pudo enviar el email a {to} ({info}). Avísale al operador.")
            except Exception:
                pass


async def _drain_sends(mb) -> None:
    """Drain orders that OPEN a conversation (V2-683): a first message to somebody, by SMTP.

    The send itself is `send_reply` with no `in_reply_to` — which is what it already does for a mail that has
    no thread to continue, so nothing new reaches the network here. The differences with a reply are the two
    that matter: the subject is the errand's own (there is no «Re:» to inherit), and the echo carries the
    order's `ref`, which is what lets whatever asked for this bind the conversation it just created."""
    if not ingest.v2_enabled() or _send_inbox is None:
        return
    for r in _send_inbox.drain():
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
            ingest.publish_msg_out(PLATFORM, {
                "chatId": to, "messageId": f"sent:{_t.time():.0f}:{to[:60]}", "ref": r.get("ref"),
                "from": "", "body": text, "timestamp": _t.time(),
                "chatName": r.get("name") or to})
        else:
            logger.warning(f"Email: fallo al escribir a {to}: {info}")
            ingest.publish_send_failed(r, str(info))
            try:
                from voice import brain_notes
                brain_notes.push(f"[SISTEMA] No se pudo escribir a {r.get('name') or to} por correo ({info}). "
                                 f"Avísale al operador; no lo he reintentado.")
            except Exception:
                pass


#: A folder page he looked at within this long is kept in step with the server; one left alone is not asked about.
MIRROR_RECENT_S = 900


def on_screen(db: dict) -> dict[str, list[str]]:
    """{folder: [uid]} of what the card shows: the pending Inbox items, and the first rows of every folder list he
    LOOKED at recently (`viewed_at`, stamped when he enters it; the card's `mailbox.lists` are keyed `folder` or
    `folder#category`). Bounded by what is on screen, never by the size of the mailbox."""
    import time as _t
    out: dict[str, list[str]] = {}
    inbox = [str(it.get("messageId")) for it in db.get("items") or []
             if it.get("platform") == PLATFORM and it.get("messageId")]
    if inbox:
        out["INBOX"] = inbox
    for key, lst in ((db.get("mailbox") or {}).get("lists") or {}).items():
        try:
            recent = _t.time() - float((lst or {}).get("viewed_at") or 0) < MIRROR_RECENT_S
        except (TypeError, ValueError):
            recent = False
        if recent:
            out.setdefault(str(key).split("#", 1)[0], []).extend(
                str(r.get("uid")) for r in (lst.get("rows") or [])[:60] if isinstance(r, dict))
    return {f: list(dict.fromkeys(u)) for f, u in out.items() if u}


def pages_to_reread(db: dict, folder: str, exists) -> list[str]:
    """The recently viewed pages of `folder` whose size changed since they were read — mail arrived, or came back
    from where he had moved it. Their first page is read again; a page read before the size was recorded is not."""
    import time as _t
    out = []
    if exists is None:
        return out
    for key, lst in ((db.get("mailbox") or {}).get("lists") or {}).items():
        if str(key).split("#", 1)[0] != folder or (lst or {}).get("exists") in (None, exists):
            continue
        try:
            if _t.time() - float(lst.get("viewed_at") or 0) < MIRROR_RECENT_S:
                out.append(str(key))
        except (TypeError, ValueError):
            logger.debug(f"Email: unreadable view time on {key!r}, not re-read")
    return out


async def _reread_first_page(mb, key: str, lst: dict | None = None) -> None:
    from connectors.email import folders as _folders
    folder, _, category = key.partition("#")
    extra = {"category": category, "routes": (lst or {}).get("routes") or []} if category else {}
    page = await asyncio.to_thread(_folders.list_page, mb, folder, None, 30, **extra)
    ingest.publish_mailbox(PLATFORM, {"folder": folder, "before": None, **page})


async def _poll_external_flags(mb) -> None:
    """Mirror what the operator did in his own mail client (V2-546, V2-807 T-04).

    Two answers per folder on screen, from one login (`membership.check`): which of those messages the folder
    STILL holds, and their flags. A mail he archived, deleted or moved elsewhere has left the folder and leaves the
    card (`connector.mailbox` `{folder, gone}`); \\Seen means he opened it and \\Answered that he replied — either
    way it has been dealt with. Per message, never a watermark: IMAP is the one source that is exact about WHICH.

    Scoped to what the card shows, so its cost is the size of the screen and not of the mailbox; nothing on
    screen, nothing asked. A folder the server could not be asked about changes nothing."""
    if not ingest.v2_enabled():
        return
    try:
        db = store.load()
    except Exception:  # noqa: BLE001
        return
    shown = on_screen(db)
    if not shown:
        return
    from connectors.email import membership
    pending = [it for it in db.get("items", []) if it.get("platform") == PLATFORM]
    for folder, uids in shown.items():
        answer = await asyncio.to_thread(membership.check, mb, folder, uids)
        left = membership.gone(uids, answer)
        if left:
            ingest.publish_mailbox(PLATFORM, {"folder": folder, "gone": left})
            logger.info(f"Email: {len(left)} left {folder} in his own client (archived, deleted or moved)")
        lists = (db.get("mailbox") or {}).get("lists") or {}
        for key in pages_to_reread(db, folder, (answer or {}).get("exists")):
            await _reread_first_page(mb, key, lists.get(key))
        if answer is None or folder.upper() != "INBOX":
            continue
        by_chat: dict[str, list[str]] = {}
        for it in pending:
            got = answer["flags"].get(str(it.get("messageId")))
            if got and ("\\Seen" in got or "\\Answered" in got):
                by_chat.setdefault(str(it.get("chatId")), []).append(str(it.get("messageId")))
        for chat_id, ids in by_chat.items():
            ingest.publish_read(PLATFORM, chat_id, ids=ids)
            logger.info(f"Email: {len(ids)} read or answered in his own client ({chat_id})")


async def _drain_history(mb) -> None:
    """Serve "load previous" (V2-546). IMAP holds the whole mailbox on the server, so this is exact: earlier
    mail from the same correspondent, and we know when we have reached the first one."""
    if _history_inbox is None:
        return
    for order in _history_inbox.drain():
        chat_id, before = order.get("chatId"), order.get("beforeId")
        if not chat_id or not before:
            ingest.publish_history(PLATFORM, chat_id, [],
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
        ingest.publish_history(PLATFORM, chat_id, rows, complete=complete)
        logger.info(f"Email: +{len(rows)} mensajes anteriores de {chat_id}")


async def _drain_fetch(mb) -> None:
    """Serve a platform-wide pull (V2-624 — «chupar más mensajes», «la actividad de las últimas 72 horas»).
    IMAP searches the whole mailbox by date, so this is exact to the cutoff DAY (the search granularity) and
    trimmed to the hour here. Everything lands in the CONVERSATIONS as read scrollback via the same
    connector.history seam "load previous" uses — never in triage: pulling the past must not interrupt.
    `parse_message`'s automated-sender filter applies on purpose: this widget is a triage surface, and the
    newsletters it never shows live are not «conversations» when pulled either."""
    if _fetch_inbox is None:
        return
    for order in _fetch_inbox.drain():
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
            ingest.publish_history(PLATFORM, chat_id, rows, name=name, is_group=False)
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
    if _mailbox_inbox is None:
        return
    from connectors.email import folders as _folders
    for order in _mailbox_inbox.drain():
        folder = str(order.get("folder") or "INBOX")
        if order.get("open"):
            msg = await asyncio.to_thread(_folders.read_one, mb, folder, str(order["open"]), _media_dir())
            ingest.publish_mailbox(PLATFORM, {"folder": folder, "open": msg})
            continue
        try:
            limit = max(1, min(100, int(order.get("limit") or 30)))
        except (TypeError, ValueError):
            limit = 30
        extra = {"category": order["category"], "routes": order.get("routes") or []} if order.get("category") else {}
        page = await asyncio.to_thread(_folders.list_page, mb, folder, order.get("before"), limit, **extra)
        ingest.publish_mailbox(PLATFORM, {"folder": folder, "before": order.get("before"), **page})


async def _drain_disposals(mb) -> None:
    """Drain archive/delete orders (V2-543) and execute them in the REAL mailbox. The widget already removed
    the item and (for trash) the confirm gate already asked; a failure is TOLD, never silently retried — same
    policy as replies."""
    if not ingest.v2_enabled():
        return
    for inbox, verb in ((_archive_inbox, "archive"), (_trash_inbox, "trash")):
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
            try:
                from voice import brain_notes
                brain_notes.push(f"[SISTEMA] No se pudo {label} el correo en el buzón real ({why}). "
                                 "Avísale al operador.")
            except Exception:
                pass


async def _loop() -> None:
    global _mark_inbox, _reply_inbox, _send_inbox, _archive_inbox, _trash_inbox, _history_inbox, _fetch_inbox
    global _unread_inbox, _mailbox_inbox
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
    await asyncio.to_thread(seed_from_mailbox, mb)
    if ingest.v2_enabled():
        if _mark_inbox is None:
            _mark_inbox = ingest.MarkReadInbox(PLATFORM)
        if _reply_inbox is None:
            _reply_inbox = ingest.ReplyInbox(PLATFORM)
        if _send_inbox is None:
            _send_inbox = ingest.SendInbox(PLATFORM)
        if _unread_inbox is None:
            _unread_inbox = ingest.MarkUnreadInbox(PLATFORM)
        if _archive_inbox is None:
            _archive_inbox = ingest.ArchiveInbox(PLATFORM)
        if _trash_inbox is None:
            _trash_inbox = ingest.TrashInbox(PLATFORM)
        if _history_inbox is None:
            _history_inbox = ingest.HistoryAskInbox(PLATFORM)
        if _fetch_inbox is None:
            _fetch_inbox = ingest.FetchInbox(PLATFORM)
        if _mailbox_inbox is None:
            _mailbox_inbox = ingest.MailboxInbox(PLATFORM)
    _set_status("connected", None, f"Conectado como {config.address()}.")
    logger.info(f"Email conectado ({config.address()}) — escuchando tu buzón")
    global _demand_task
    if _demand_task is None or _demand_task.done():
        _demand_task = asyncio.create_task(_serve_demands(mb))
    while True:
        # What the OPERATOR is waiting for goes first (demo pass 48, 2026-09-29: the receipt's history order,
        # asked at E1, landed 43 s later — after this tick's new-mail fetch, flag poll and the rest, each its own
        # IMAP login — with «open it» and the forward already failed). `_nap` wakes on these same three orders.
        for what, fn in (("sends", _drain_sends), ("history", _drain_history), ("fetch", _drain_fetch),
                         ("mailbox", _drain_mailbox)):
            try:
                await fn(mb)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Email {what} tick (first): {e}")
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
        try:
            await _drain_disposals(mb)
        except Exception as e:
            logger.debug(f"Email disposal tick: {e}")
        for what, fn in (("sends", _drain_sends), ("unreads", _drain_unreads), ("flags", _poll_external_flags),
                         ("history", _drain_history), ("fetch", _drain_fetch)):
            try:
                await fn(mb)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Email {what} tick: {e}")
        await _nap(config.poll_interval())


_NAP_STEP_S = 0.5


def _on_demand() -> tuple:
    """The queues an operator waits on: a send, a history order, a pull, a folder page."""
    return (_history_inbox, _send_inbox, _fetch_inbox, _mailbox_inbox)
_demand_task: "asyncio.Task | None" = None


async def _serve_demands(mb) -> None:
    """The operator's on-demand orders — a send, a history fetch, a pull — served the moment they arrive, beside the
    poll loop instead of inside it (demo pass 48: an order that arrives while a tick is mid-housekeeping waited for
    the whole tick, 43 s, and the next two turns failed). Each drain opens its own IMAP/SMTP connection, so running
    beside the housekeeping costs nothing but a second login; a queue is taken once, so nothing is done twice."""
    while True:
        try:
            if any(i is not None and i.pending() for i in _on_demand()):
                for what, fn in (("sends", _drain_sends), ("history", _drain_history), ("fetch", _drain_fetch),
                                ("mailbox", _drain_mailbox)):
                    try:
                        await fn(mb)
                    except Exception as e:  # noqa: BLE001
                        logger.debug(f"Email {what} (on demand): {e}")
            await asyncio.sleep(_NAP_STEP_S)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Email demand loop: {e}")
            await asyncio.sleep(_NAP_STEP_S)


async def _nap(total: float) -> None:
    """Sleep until the next poll — or until an ON-DEMAND order arrives (demo pass 31, E2: «did inworld send me
    something?» asked the mailbox for the receipt, «open it» came 14 s later, and the mail landed 3 s after that:
    the history order had waited out the 20 s poll). A send, a history or a fetch order is the operator waiting."""
    loop = asyncio.get_running_loop()
    end = loop.time() + max(0.0, float(total))
    while loop.time() < end:
        if any(i is not None and i.pending() for i in _on_demand()):
            return
        await asyncio.sleep(min(_NAP_STEP_S, max(0.0, end - loop.time())))


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
    global _task, _mark_inbox, _reply_inbox, _send_inbox, _archive_inbox, _trash_inbox, _unread_inbox
    global _demand_task
    if _task:
        _task.cancel()
        _task = None
    if _demand_task:
        _demand_task.cancel()
        _demand_task = None
    for inbox in (_mark_inbox, _reply_inbox, _send_inbox, _archive_inbox, _trash_inbox, _unread_inbox):
        try:
            if inbox is not None:
                inbox.close()
        except Exception:
            pass
    _mark_inbox = _reply_inbox = _send_inbox = _archive_inbox = _trash_inbox = _unread_inbox = None
    _seen.clear()
    _set_unread_total(-1)
    _published.clear()
    _shown.clear()
