#
# service.py — WhatsApp connector ENGINE integrated into zaelar (INI-014; unified store in INI-015). Runs in the
# server lifespan (gated by WA_ENABLED, always-on). Starts the bridge (observe), then loops: reads state+QR, triages
# new messages with the SHARED LOCAL model, and WRITES the UNIFIED messaging store
# (widgets/_data/mensajeria.json, platform="whatsapp") — the same one Telegram also writes. Also drains operator
# orders (pending_read for its platform) by calling the bridge (actual mark-read).
#
# Boundary: none of this touches ~/.hermes/hermes-agent (vendored bridge). Triage does NOT go through the Hermes
# agent (privacy + voice ACP invariant). See .meshkore/docs/architecture/zaelar-hermes-federation.md.
#
import asyncio

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


def _set_status(status: str, qr=None) -> None:
    try:
        if ingest.v2_enabled():
            ingest.publish_status(PLATFORM, status, qr)     # stateless: widget reflects state+QR
        else:
            store.set_platform_status(PLATFORM, status, qr)
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
        if not chat_id or not text:
            continue
        try:
            await client.send_message(chat_id, text, reply_to=r.get("messageId") or None)
            logger.info(f"WhatsApp: respuesta enviada a {chat_id}")
            _note(f"[SISTEMA] WhatsApp enviado a {r.get('to') or chat_id}. Confírmaselo al operador de forma natural.")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"WhatsApp: fallo al enviar a {chat_id}: {e}")
            _note(f"[SISTEMA] No se pudo enviar el WhatsApp a {r.get('to') or chat_id} ({e}). Avísale al operador.")


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
        if not chat_id or not text:
            continue
        try:
            res = await client.send_message(chat_id, text)
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
                "chatName": r.get("name") or ""})
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
                                             int(order.get("limit") or 30))
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
    global _mark_inbox, _reply_inbox, _send_inbox, _history_inbox, _contacts_inbox
    _set_status("starting", None)
    if _contacts_inbox is None:
        _contacts_inbox = ingest.ContactsInbox(PLATFORM)   # V2-714: the address book
    if ingest.v2_enabled() and _mark_inbox is None:
        _mark_inbox = ingest.MarkReadInbox(PLATFORM)     # subscription in THIS loop (server) -> direct delivery
        _reply_inbox = ingest.ReplyInbox(PLATFORM)       # V2-521: dictated replies, same delivery path
        _send_inbox = ingest.SendInbox(PLATFORM)         # V2-683: opening a conversation
        _history_inbox = ingest.HistoryAskInbox(PLATFORM)  # V2-546: "load previous"
    try:
        await bridge.start()
    except Exception as e:
        logger.error(f"WhatsApp: no se pudo arrancar el bridge: {e}")
        _set_status("off", None)
        return
    connected = False
    while True:
        try:
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
                                 ("contacts", _drain_contacts)):
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
