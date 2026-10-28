#
# directory.py — the ACCOUNT as the bridge knows it: address book (V2-714), chat list, pairing history into the
# archive, new groups, «mark as unread» and mark-read.
#
import time

from loguru import logger

from connectors.messaging import ingest, store
from connectors.whatsapp import client
from connectors.whatsapp import service as _svc

PLATFORM = _svc.PLATFORM


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
    if _svc._contacts_inbox is None:
        return
    for _order in _svc._contacts_inbox.drain():
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
        entries = [e for e in (_svc._history_entry(m) for m in msgs) if e.get("ts")]
        n += archive.record(PLATFORM, chat_id, entries, chat_name=str(msgs[0].get("chatName") or ""),
                            is_group=bool(msgs[0].get("isGroup")))
    logger.info(f"WhatsApp: pairing history → {n} new message(s) archived from {len(by_chat)} chat(s)")


async def _drain_unread() -> None:
    """Put chats back to unread on the phone («déjalo como no leído»). Told once on failure, never retried."""
    if _svc._unread_inbox is None:
        return
    for k in _svc._unread_inbox.drain():
        try:
            await client.mark_unread(k)
            logger.info(f"WhatsApp: chat {k.get('chatId')} marcado como no leído")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"WhatsApp: no pude marcar como no leído {k.get('chatId')}: {e}")
            _svc._note(f"[SISTEMA] No pude dejar como no leído ese chat de WhatsApp ({e}). Díselo al operador.")


async def _drain_groups() -> None:
    """Create the groups the operator asked for. Members arrive resolved (a JID, or a phone that `_jid` turns
    into one); the new group is handed back as a chat-list row, and a first message goes in if there was one."""
    if _svc._group_inbox is None:
        return
    for order in _svc._group_inbox.drain():
        members = [m for m in (str((x or {}).get("chatId") or "").strip() or _svc._jid((x or {}).get("to"))
                               for x in order.get("members") or []) if m]
        name = str(order.get("name") or "").strip()
        try:
            got = await client.create_group(name, members)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"WhatsApp: no pude crear el grupo {name}: {e}")
            ingest.publish_send_failed(order, str(e))
            _svc._note(f"[SISTEMA] No pude crear el grupo de WhatsApp «{name}» ({e}). Díselo al operador.")
            continue
        gid = str((got or {}).get("id") or "")
        logger.info(f"WhatsApp: grupo creado {gid} con {len(members)} miembro(s)")
        ingest.publish_chats(PLATFORM, [{"chatId": gid, "name": name, "kind": "group", "ts": time.time(),
                                         "preview": ""}])
        text, files = str(order.get("text") or "").strip(), order.get("attachments") or []
        if gid and (text or files):
            try:
                await _svc._send(gid, text, files)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"WhatsApp: grupo creado, primer mensaje no enviado: {e}")
        _svc._note(f"[SISTEMA] Grupo de WhatsApp «{name}» creado con {len(members)} persona(s). Díselo al operador.")


async def _drain_chats() -> None:
    """Serve one page of the chat list. WhatsApp keeps no server-side list a linked device can page through:
    the bridge answers from the book it has been told since pairing (see `client.get_chats`)."""
    if _svc._chats_inbox is None:
        return
    for order in _svc._chats_inbox.drain():
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
    keys = (_svc._mark_inbox.drain() if _svc._mark_inbox else []) if v2 else store.take_pending_read(PLATFORM)
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
