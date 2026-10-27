#
# service.py — WhatsApp connector ENGINE integrated into zaelar (unified store in connectors/messaging). Runs in the
# server lifespan (gated by WA_ENABLED, always-on). Starts the bridge (observe), then loops: reads state+QR, triages
# new messages with the SHARED LOCAL model, and WRITES the UNIFIED messaging store
# (widgets/_data/mensajeria.json, platform="whatsapp") — the same one Telegram also writes. Also drains operator
# orders (pending_read for its platform) by calling the bridge (actual mark-read).
#
# Boundary: triage runs in this engine and never through an outside agent (privacy + voice ACP invariant).
#
import asyncio
import time

from loguru import logger

from connectors.messaging import ingest, notify, store, triage
from connectors.whatsapp import client, config
from connectors.whatsapp.bridge_proc import bridge

PLATFORM = "whatsapp"

_task: asyncio.Task | None = None
_seen: set[str] = set()          # already shown messageIds (to avoid resurrecting what the operator removed)
_published: set[str] = set()     # v2 stateless: messageIds already published to bus (dedup before widget triage)
_mark_inbox = None               # v2 stateless: msg.mark_read subscription (created in the loop; see ingest.py)
_reply_inbox = None              # V2-521: msg.reply subscription (created in the loop)
_send_inbox = None               # V2-683: msg.send — writing to somebody who has not written
_history_inbox = None            # V2-546: msg.history subscription (created in the loop)


def enabled() -> bool:
    # UI-MANAGED CONFIG: store (written by the UI when clicking "Connect WhatsApp") wins; if it says nothing, fall
    # back to WA_ENABLED (back-compat / power-user). See config/connectors.py.
    from config import connectors as _store
    return _store.enabled("whatsapp")


def _set_status(status: str, qr=None, detail=None) -> None:
    try:
        if ingest.v2_enabled():
            ingest.publish_status(PLATFORM, status, qr, detail)   # stateless: widget reflects state+QR+reason
        else:
            store.set_platform_status(PLATFORM, status, qr, detail)
    except Exception as e:
        logger.debug(f"WhatsApp set_status: {e}")


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
            ingest.publish_history(PLATFORM, chat_id, [_history_entry(m) for m in rows])
    # The bridge also tags each message with its DIRECTION. An outbound one (the operator wrote from his own
    # phone, or zaelar sent it for him) must never reach triage or notification: it is not news and it is not a
    # decision. It goes to the conversation and marks that chat as seen.
    outgoing = [m for m in msgs if m.get("direction") == "out"]
    msgs = [m for m in msgs if m.get("direction") != "out"]
    if outgoing and ingest.v2_enabled():
        sent = 0
        for m in outgoing:
            mid = m.get("messageId")
            if mid and mid not in _published:
                _published.add(mid)
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
            if mid and mid not in _published:
                _published.add(mid)
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
        _seen.add(v.get("messageId"))
        who, group = _origin(v)
        v["from"], v["group"] = who, group          # normalize to unified-store shape
    store.upsert_items(PLATFORM, fresh)
    notice = notify.deserving(fresh)
    logger.info(f"WhatsApp: +{len(fresh)} ({len(notice)} avisan)")
    if notice:
        await notify.announce("WhatsApp", notice)


_contacts_inbox = None           # V2-714: msg.contacts subscription
_chats_inbox = None              # msg.chats: one page of the chat list
_group_inbox = None              # msg.group: creating a group
_unread_inbox = None             # msg.mark_unread: «déjalo como no leído»


def _wa_person(c: dict) -> dict | None:
    """One WhatsApp contact as the normalised row `widgets/contactos/imports.py` folds in.

    The NAME is the one HE saved (`name`); `notify` — the nickname the other person set for themselves —
    only fills a blank. It is deliberately never an identity key either: it changes whenever they feel
    like it and two strangers share it all the time (`imports.match` says the same thing from its side).
    """
    jid = str(c.get("id") or "").strip()
    if not jid or "@g.us" in jid:
        return None                      # a group arrives as a GROUP, not as a person
    phone = str(c.get("phoneNumber") or "").strip() or jid.split("@")[0]
    if phone and not phone.startswith("+"):
        phone = f"+{phone}"
    name = str(c.get("name") or "").strip() or str(c.get("verifiedName") or "").strip() \
        or str(c.get("notify") or "").strip() or phone
    if not name:
        return None
    row = {"name": name, "kind": "person", "phone": phone,
           "channels": [{"platform": "whatsapp", "handle": phone, "chatId": jid}],
           "externalIds": {"whatsapp": jid}}
    if c.get("imgUrl") and str(c["imgUrl"]) != "changed":
        row["avatar"] = str(c["imgUrl"])
    return row


async def _drain_contacts() -> None:
    """Hand over the address book when the contacts widget asks (V2-714).

    ⚠️ This platform cannot be asked for «everything» — the bridge reports what its socket has told it so
    far and flags `partial`. The card says «sincronizando, N hasta ahora» rather than a total, because a
    total we cannot know is the kind of promise this engine has already paid for three times."""
    if _contacts_inbox is None:
        return
    for _order in _contacts_inbox.drain():
        people, groups, err, partial = [], [], "", True
        try:
            got = await client.get_contacts()
            for c in got.get("contacts") or []:
                row = _wa_person(c)
                if row:
                    people.append(row)
            for g in got.get("groups") or []:
                subject = str(g.get("subject") or "").strip()
                gid = str(g.get("id") or "").strip()
                if not subject or not gid:
                    continue
                # Members are NOT enumerated here: the bridge knows a group's subject from its traffic,
                # not its roster, and inventing an empty roster would read as «nobody is in it».
                groups.append({"name": subject, "platform": "whatsapp", "subtype": "group",
                               "externalIds": {"whatsapp": gid},
                               "channels": [{"platform": "whatsapp", "chatId": gid}],
                               "members": []})
            partial = bool(got.get("partial", True))
        except Exception as e:  # noqa: BLE001
            err = f"WhatsApp no me dejó leer los contactos: {e}"
            logger.warning(err)
        ingest.publish_contacts("whatsapp", people, groups, partial=partial, error=err)
        logger.info(f"WhatsApp contactos → {len(people)} personas, {len(groups)} grupos (parcial={partial})")


def _chat_row(c: dict) -> dict | None:
    """A chat-book row in the platform-agnostic shape of `ingest.publish_chats`."""
    cid = str(c.get("id") or "").strip()
    if not cid:
        return None
    return {"chatId": cid, "name": str(c.get("name") or cid.split("@")[0]),
            "kind": "group" if c.get("isGroup") else "person", "unread": int(c.get("unread") or 0),
            "ts": float(c.get("ts") or 0), "preview": str(c.get("preview") or ""),
            "mediaType": str(c.get("mediaType") or ""), "fromMe": bool(c.get("fromMe")),
            "archived": bool(c.get("archived")), "pinned": bool(c.get("pinned")), "muted": bool(c.get("muted")),
            "lastId": str(c.get("lastId") or "")}


async def _drain_sync() -> None:
    """The history the phone sends at pairing, into the communications archive — and nowhere else: it is the
    account's past, not news (connectors/messaging/history.py, mode «at_link»)."""
    rows = await client.get_sync()
    if not rows:
        return
    from connectors.messaging import archive
    by_chat: dict[str, list[dict]] = {}
    for m in rows:
        by_chat.setdefault(str(m.get("chatId")), []).append(m)
    n = 0
    for chat_id, msgs in by_chat.items():
        entries = [e for e in (_history_entry(m) for m in msgs) if e.get("ts")]
        n += archive.record(PLATFORM, chat_id, entries, chat_name=str(msgs[0].get("chatName") or ""),
                            is_group=bool(msgs[0].get("isGroup")))
    logger.info(f"WhatsApp: pairing history → {n} new message(s) archived from {len(by_chat)} chat(s)")


async def _drain_unread() -> None:
    """Put chats back to unread on the phone («déjalo como no leído»). Told once on failure, never retried."""
    if _unread_inbox is None:
        return
    for k in _unread_inbox.drain():
        try:
            await client.mark_unread(k)
            logger.info(f"WhatsApp: chat {k.get('chatId')} marcado como no leído")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"WhatsApp: no pude marcar como no leído {k.get('chatId')}: {e}")
            _note(f"[SISTEMA] No pude dejar como no leído ese chat de WhatsApp ({e}). Díselo al operador.")


async def _drain_groups() -> None:
    """Create the groups the operator asked for. Members arrive resolved (a JID, or a phone that `_jid` turns
    into one); the new group is handed back as a chat-list row, and a first message goes in if there was one."""
    if _group_inbox is None:
        return
    for order in _group_inbox.drain():
        members = [m for m in (str((x or {}).get("chatId") or "").strip() or _jid((x or {}).get("to"))
                               for x in order.get("members") or []) if m]
        name = str(order.get("name") or "").strip()
        try:
            got = await client.create_group(name, members)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"WhatsApp: no pude crear el grupo {name}: {e}")
            ingest.publish_send_failed(order, str(e))
            _note(f"[SISTEMA] No pude crear el grupo de WhatsApp «{name}» ({e}). Díselo al operador.")
            continue
        gid = str((got or {}).get("id") or "")
        logger.info(f"WhatsApp: grupo creado {gid} con {len(members)} miembro(s)")
        ingest.publish_chats(PLATFORM, [{"chatId": gid, "name": name, "kind": "group", "ts": time.time(),
                                         "preview": ""}])
        text, files = str(order.get("text") or "").strip(), order.get("attachments") or []
        if gid and (text or files):
            try:
                await _send(gid, text, files)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"WhatsApp: grupo creado, primer mensaje no enviado: {e}")
        _note(f"[SISTEMA] Grupo de WhatsApp «{name}» creado con {len(members)} persona(s). Díselo al operador.")


async def _drain_chats() -> None:
    """Serve one page of the chat list. WhatsApp keeps no server-side list a linked device can page through:
    the bridge answers from the book it has been told since pairing (see `client.get_chats`)."""
    if _chats_inbox is None:
        return
    for order in _chats_inbox.drain():
        before = order.get("before")
        try:
            limit = max(1, min(100, int(order.get("limit") or 20)))
            got = await client.get_chats(before, limit)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"WhatsApp chat list: {e}")
            ingest.publish_chats(PLATFORM, [], before=before, error=str(e))
            continue
        rows = [r for c in got.get("chats") or [] if (r := _chat_row(c))]
        nxt = min((r["ts"] for r in rows if r["ts"]), default=None)
        ingest.publish_chats(PLATFORM, rows, before=before, next_before=nxt,
                             complete=bool(got.get("complete")))
        logger.info(f"WhatsApp: chat list page → {len(rows)} of {got.get('known')} known")


async def _drain_reads() -> None:
    v2 = ingest.v2_enabled()
    keys = (_mark_inbox.drain() if _mark_inbox else []) if v2 else store.take_pending_read(PLATFORM)
    if not keys:
        return
    # The bridge expects {chatId, messageId, senderId}; the key adds `platform` -> remove it before sending.
    payload = [{"chatId": k.get("chatId"), "messageId": k.get("messageId"), "senderId": k.get("senderId")}
               for k in keys]
    try:
        await client.mark_read(payload)
    except Exception as e:
        logger.warning(f"WhatsApp mark-read falló (reintento luego): {e}")
        if v2:
            for k in keys:                       # re-publish to bus -> retry on next tick
                ingest.publish_mark_read(k)
        else:
            store.requeue_pending_read(keys)


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
    if not ingest.v2_enabled() or _reply_inbox is None:
        return
    for r in _reply_inbox.drain():
        chat_id = str(r.get("chatId") or r.get("to") or "").strip()
        text = (r.get("text") or "").strip()
        files = r.get("attachments") or []
        if not chat_id or not (text or files):
            continue
        try:
            res = await _send(chat_id, text, files, reply_to=r.get("messageId") or None)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"WhatsApp: fallo al enviar a {chat_id}: {e}")
            # V2-819 — and the card that sent it hears it too: its row keeps his text and says why.
            ingest.publish_send_failed({**r, "platform": PLATFORM}, str(e))
            _note(f"[SISTEMA] No se pudo enviar el WhatsApp a {r.get('to') or chat_id} ({e}). Avísale al operador.")
            continue
        logger.info(f"WhatsApp: respuesta enviada a {chat_id}")
        _note(f"[SISTEMA] WhatsApp enviado a {r.get('to') or chat_id}. Confírmaselo al operador de forma natural.")
        _echo_sent(r, chat_id, text, files, res)


def _echo_sent(r: dict, chat_id: str, text: str, files: list, res: dict | None) -> None:
    """V2-819 — a reply that LEFT joins its conversation now, under the id WhatsApp gave it (the phone's own echo
    of the same message then lands on the same row), and carries the order's `ref` so the card that sent it
    knows. Outside the send's try on purpose: failing to RECORD a message is not failing to SEND it."""
    try:
        import time as _t
        mid = (res or {}).get("messageId") or f"sent:{_t.time():.0f}"
        _published.add(mid)
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
    if not ingest.v2_enabled() or _send_inbox is None:
        return
    for r in _send_inbox.drain():
        chat_id = str(r.get("chatId") or "").strip() or _jid(r.get("to"))
        text = (r.get("text") or "").strip()
        files = r.get("attachments") or []
        if not chat_id or not (text or files):
            continue
        try:
            res = await _send(chat_id, text, files)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"WhatsApp: fallo al escribir a {chat_id}: {e}")
            ingest.publish_send_failed(r, str(e))
            _note(f"[SISTEMA] No pude escribir a {r.get('name') or chat_id} por WhatsApp ({e}). Puede que ese "
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
    if _history_inbox is None:
        return
    for order in _history_inbox.drain():
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


def _note(text: str) -> None:
    try:
        from voice import brain_notes
        brain_notes.push(text)
    except Exception:
        pass


async def _loop() -> None:
    global _mark_inbox, _reply_inbox, _send_inbox, _history_inbox, _contacts_inbox, _chats_inbox, _group_inbox
    global _unread_inbox
    _set_status("starting", None)
    if _contacts_inbox is None:
        _contacts_inbox = ingest.ContactsInbox(PLATFORM)   # V2-714: the address book
    if _chats_inbox is None:
        _chats_inbox = ingest.ChatsInbox(PLATFORM)         # the chat list
    if _group_inbox is None:
        _group_inbox = ingest.GroupInbox(PLATFORM)         # new groups
    if _unread_inbox is None:
        _unread_inbox = ingest.MarkUnreadInbox(PLATFORM)   # back to unread
    if ingest.v2_enabled() and _mark_inbox is None:
        _mark_inbox = ingest.MarkReadInbox(PLATFORM)     # subscription in THIS loop (server) -> direct delivery
        _reply_inbox = ingest.ReplyInbox(PLATFORM)       # V2-521: dictated replies, same delivery path
        _send_inbox = ingest.SendInbox(PLATFORM)         # V2-683: opening a conversation
        _history_inbox = ingest.HistoryAskInbox(PLATFORM)  # V2-546: "load previous"
    try:
        await bridge.start()
    except Exception as e:
        # The reason travels to the card. An «off» with no reason is how a bridge that could never start in a
        # container stayed invisible: the card said «Preparando la conexión…» forever.
        logger.error(f"WhatsApp: no se pudo arrancar el bridge: {e}")
        _set_status("error", None, str(e))
        return
    connected = False
    while True:
        try:
            if bridge.proc is not None and bridge.proc.returncode is not None:
                # The bridge died under us. Nothing else restarts it, and the card would wait on a QR that no
                # process is going to produce — relaunch it; the paired session on disk makes that silent.
                logger.warning(f"WhatsApp: el bridge murió (exit {bridge.proc.returncode}) — lo relanzo")
                connected = False
                _set_status("connecting", None)
                await bridge.start()
            h = await client.health()
            st = (h or {}).get("status", "connecting")
            if st == "connected":
                if not connected:
                    logger.info("WhatsApp conectado — escuchando tu buzón")
                connected = True
                _set_status("connected", None)
                await _ingest_new()
                await _drain_reads()
                await _drain_replies()
                for what, fn in (("sends", _drain_sends),
                                 ("read marks", _drain_external_reads), ("history", _drain_history),
                                 ("contacts", _drain_contacts), ("chats", _drain_chats),
                                 ("groups", _drain_groups), ("unread", _drain_unread), ("sync", _drain_sync)):
                    try:
                        await fn()
                    except Exception as e:  # noqa: BLE001
                        logger.debug(f"WhatsApp {what} tick: {e}")
            else:
                connected = False
                _set_status("connecting", (h or {}).get("qr"))
        except Exception as e:
            logger.debug(f"WhatsApp tick: {e}")
        await asyncio.sleep(config.poll_interval())


def start() -> None:
    """Start the engine as a background task (call from server lifespan if WA_ENABLED=1)."""
    global _task
    if not enabled():
        _set_status("off", None)
        logger.info("WhatsApp: desactivado (WA_ENABLED!=1)")
        return
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info("WhatsApp: motor arrancado")


async def stop() -> None:
    global _task
    if _task:
        _task.cancel()
        _task = None
    await bridge.stop()
