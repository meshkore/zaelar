"""Messaging actions that WRITE to somebody: reply, draft, send_draft, cancel_send, send_to and forward.

Every module-level name of `data` is read through it (`_d.<name>`), so a patch on `data` still governs every call.
"""
from __future__ import annotations

from .. import data as _d


# Reply to a message (V2-051): enqueue into pending_reply for the platform's connector; the CONFIRM gate (V2-025)
# already asked. `n` is a message in the open thread, or a CHAT (its last message) in the chat list.
def _a_reply(action, payload) -> dict:
    # Contract kept (V2-521, tested): the same `n` duality as `hide`. `draft`/`send_draft` are the unambiguous
    # path, where `n`/`messageId` name one ITEM.
    n = payload.get("n")
    text = (payload.get("text") or "").strip()
    if n is not None and text:
        db = _d.load_db()
        target = None
        if db.get("active_chat") is not None:
            target = next((it for it in _d._renumber(db.get("items", [])) if it.get("n") == n), None)
        else:
            chat = next((c for c in _d._group_chats(_d._visible_items(db)) if c.get("n") == n), None)
            if chat:                       # chat -> its last message, for threading/recipient
                key = (chat["platform"], str(chat["chatId"]))
                msgs = [it for it in db.get("items", [])
                        if (it.get("platform"), str(it.get("chatId"))) == key]
                target = msgs[-1] if msgs else None
        if target is not None:
            _d._outbound.enqueue_reply(db, target, text)
            _d.store.save(_d.WIDGET_ID, db)
            return _d.view_data()
        # A reply with nothing to answer is a send that did not happen and must SAY so: what leaves the machine is
        # never claimed without the act.
        return {"ok": False, "error": _NO_TARGET_FOR_THE_MODEL, "message": _no_reply_target(db), "say": _no_reply_say(db)}
    if n is not None and not text:
        return _d.view_data()                      # nothing dictated: nothing to send and nothing to claim
    db = _d.load_db()
    if text and db.get("active_chat") is not None:
        # No number, a conversation OPEN: «contéstale que sí» means the person on screen — the same resolution
        # the compose box uses (`resolve_reply_target`). Without it the model had to invent an `n` for a chat
        # it was already inside, and a reply dictated there was lost.
        target = _d._outbound.resolve_reply_target(db)
        if target is not None:
            _d._outbound.enqueue_reply(db, target, text)
            _d.store.save(_d.WIDGET_ID, db)
            return _d.view_data()
    return {"ok": False, "error": _NO_TARGET_FOR_THE_MODEL, "message": _no_reply_target(db), "say": _no_reply_say(db)}


_NO_TARGET_FOR_THE_MODEL = ("no_target: no hay ningún mensaje con ese número al que contestar. Para escribir a alguien que no "
                            "ha escrito, llama a send_to con `contact` y `channel`; si el canal no está conectado, "
                            "díselo al operador y no afirmes ningún envío.")


def _no_reply_say(db: dict) -> str:
    """The same sentence as an i18n key, so a session in any language hears it (`refusal_line.speakable`)."""
    plats = db.get("platforms") or {}
    offline = all(str((plats.get(p) or {}).get("status") or "off") in ("off", "disconnected")
                  for p in _d._outbound.PLATFORMS)
    return "widgets.mensajeria.refusal_no_conversation" + ("_offline" if offline else "")


def _no_reply_target(db: dict) -> str:
    """The sentence a reply that had no message to answer comes back with: what is missing, and the way out."""
    plats = db.get("platforms") or {}
    off = [_d._outbound.label(p) for p in _d._outbound.PLATFORMS
           if str((plats.get(p) or {}).get("status") or "off") in ("off", "disconnected")]
    tail = (f" {', '.join(off)} no {'está conectado' if len(off) == 1 else 'están conectados'} — se conectan en "
            f"⚙ Conectores.") if off else ""
    return "No tengo esa conversación para contestarla, así que no se ha enviado nada." + tail


# DRAFT then SEND (V2-611): a draft fills a visible box he reads before anything leaves; `send_draft` is the
# separate act that sends (button or «envíalo»). `reply` stays the one-shot, CONFIRM-gated path.
def _a_draft(action, payload) -> dict:
    db = _d.load_db()
    if str(payload.get("contact") or "").strip() and payload.get("n") is None and not payload.get("messageId"):
        return _draft_new(db, payload)
    target = _d._outbound.resolve_reply_target(db, payload.get("n"), payload.get("messageId"))
    if target is None:
        return {"ok": False, "error": "no_target",
                 "message": "No sé a qué conversación o mensaje se refiere el borrador."}
    out = _d._drafts.write(db, target, str(payload.get("text") or ""), bool(payload.get("reply_all")),
                           files=payload.get("files"))
    _d.store.save(_d.WIDGET_ID, db)
    return out


def _draft_new(db: dict, payload: dict) -> dict:
    """A NEW message held for his word (V2-800): resolved to WHO and HOW exactly like `send_to`, written into the
    card's draft box, and nothing leaves. `send_draft` (now, or with `at`/`in_minutes`) is what sends it."""
    t = _d._outbound.resolve_target(payload)
    if not t.get("ok"):
        return t
    target = {**t, "new": True, "subject": str(payload.get("subject") or "").strip()}
    out = _d._drafts.write(db, target, str(payload.get("text") or ""), False, files=payload.get("files"))
    _d.store.save(_d.WIDGET_ID, db)
    return {**out, "held": True, "to": t.get("name"), "channel": t.get("platform"),
            "message": "Ya está escrito: revísalo y confírmame si lo mando ya o cuándo."}


def _a_cancel_send(action, payload) -> dict:
    """Stop a scheduled send before it leaves (V2-800) — by `ref`, by recipient, or the only one scheduled."""
    db = _d.load_db()
    out = _d._held.cancel(db, ref=str(payload.get("ref") or ""), contact=str(payload.get("contact") or ""))
    if out.get("ok"):
        _d.store.save(_d.WIDGET_ID, db)
    return out


def _a_send_draft(action, payload) -> dict:
    from .. import card_send as _card
    if _card.is_card_send(payload):     # V2-819: the card's own Send — its text, its conversation, answered
        return _card.send(payload)
    db = _d.load_db()
    # The widget's button names WHICH conversation; a bare voice «envíalo» gets the most recent draft. A held NEW
    # message is named by its recipient (`contact`), and `at`/`in_minutes` schedule it (V2-800).
    not_before, bad = _d._held.when(payload)
    if bad:
        return {"ok": False, "error": bad, "message": "No entiendo para cuándo: dime la hora o dentro de cuánto."}
    key = _d._held.draft_for(db, str(payload.get("contact") or "")) if payload.get("contact") else None
    if str(payload.get("key") or "") in (db.get("drafts") or {}):
        key = str(payload["key"])         # the draft screen's own button names its draft exactly
    elif payload.get("contact") and key is None:
        return {"ok": False, "error": "no_draft", "message": "No tengo ningún borrador para esa persona."}
    if key is None and (payload.get("n") is not None or payload.get("messageId")):
        t = _d._outbound.resolve_reply_target(db, payload.get("n"), payload.get("messageId"))
        if t is not None:
            key = _d._drafts.key(t)
    draft = _d._drafts.pick(db, key)
    text = str(draft.get("text") or "").strip()
    files = _d._media.local_paths(_d.store.data_dir(_d.WIDGET_ID), draft.get("files"))
    if not text and not files:
        return {"ok": False, "error": "no_draft", "message": "No hay ningún borrador que enviar."}
    stored = draft.get("target") or {}
    # Re-resolve against the LIVE item so a stale identity is not blindly replied to; the stored platform/chatId
    # are the fallback, enough to send with no pending item left.
    if stored.get("new"):
        order = _d._outbound.enqueue(db, stored, text, subject=str(stored.get("subject") or ""),
                                     attachments=files, not_before=not_before, scheduled=bool(not_before))
        _d._drafts.forget(db, draft.get("key") or key)
        _d.store.save(_d.WIDGET_ID, db)
        return {"ok": True, "to": stored.get("name") or stored.get("to"), "text": text, "ref": order.get("ref"),
                "attachments": len(files), **({"scheduled_for": not_before} if not_before else {})}
    target = _d._outbound.resolve_reply_target(db, stored.get("n"), stored.get("messageId")) or stored
    cc = _d._drafts.cc_for(draft)
    _d._outbound.enqueue_reply(db, target, text, cc=cc, attachments=files, not_before=not_before)
    _d._drafts.forget(db, draft.get("key") or key)
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, "to": target.get("senderId") or target.get("chatId"), "text": text,
            "cc": list(cc), "attachments": len(files), **({"scheduled_for": not_before} if not_before else {})}


def _a_send_to(action, payload) -> dict:
    # Writing to a PERSON who has not written (V2-683): WHO and WHICH channel resolve in `outbound.py`; an
    # unresolved one is a refusal saying what is missing — words to the WRONG person cannot be taken back.
    db = _d.load_db()
    t = _d._outbound.resolve_target(payload)
    if not t.get("ok"):
        return t
    # FORWARDING: `attach_from` names a message on the card (`n`, `messageId`, or `{}` for the open one) whose files
    # travel with this send. Asked for and absent is a refusal, never a mail announcing a missing attachment.
    atts = []
    if "attach_from" in payload:
        ref = payload.get("attach_from")
        ref = ref if isinstance(ref, dict) else ({"n": ref} if str(ref or "").strip() else {})
        atts = _d._outbound.attachments_of(db, ref)
        if not atts:
            return {"ok": False, "error": "no_attachment",
                    "message": "Ese mensaje no tiene adjuntos que pueda enviar — ábrelo o dime cuál es."}
    # Files the operator picked in the card (uploads) travel the same way, on every platform.
    if payload.get("files"):
        atts += [p for p in _d._media.local_paths(_d.store.data_dir(_d.WIDGET_ID), payload.get("files"))
                 if p not in atts]
    # A chat message is written on screen before it leaves (`_composing`); an email is a document, not a
    # line typed into a conversation, and goes straight out.
    if atts and (dup := _d._outbound.same_files_just_sent(db, t, atts)):
        # The same files to the same person seconds later are one send: reported as done, never queued again.
        return {"ok": True, "result": {"to": t.get("name"), "channel": t.get("platform"), "ref": dup.get("ref"),
                                       "attachments": len(atts), "already_sent": True}}
    seen = t.get("platform") != "email" and bool(str(t.get("chatId") or "").strip())
    send_at = _d.time.time() + _d._compose_seconds(payload.get("text")) if seen else 0.0
    order = _d._outbound.enqueue(db, t, payload.get("text"), subject=str(payload.get("subject") or ""),
                              objective=str(payload.get("objective") or ""), attachments=atts,
                              not_before=send_at)
    if seen:
        db["active_chat"] = {"platform": t.get("platform"), "chatId": t.get("chatId")}
        db["composing"] = {"ref": order.get("ref"), "platform": t.get("platform"), "chatId": t.get("chatId"),
                           "name": t.get("name") or "", "text": str(payload.get("text") or ""),
                           "started": _d.time.time(), "send_at": send_at}
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, "result": {"to": t.get("name"), "channel": t.get("platform"),
                                   "ref": order.get("ref"), "attachments": len(atts)}}


def _a_forward(action, payload) -> dict:
    # FORWARD = a send to a person carrying the files of a message that arrived: one name for what he asks, so the
    # model does not reach for `reply` (to the sender) and lose the files.
    src = {k: payload[k] for k in ("n", "messageId", "from") if payload.get(k) not in (None, "")}
    db0 = _d.load_db()
    orig = _d._outbound._message_ref(db0, src) or {}
    subj = str(payload.get("subject") or "").strip() or (f"Fwd: {orig.get('subject')}" if orig.get("subject") else "Fwd")
    text = str(payload.get("text") or "").strip() or subj
    # The channel is the one he names («por WhatsApp»); mail when he names none, as it always was.
    channel = str(payload.get("channel") or payload.get("platform") or "email").strip().lower()
    return _d.apply_action("send_to", {"contact": payload.get("contact") or payload.get("to"), "channel": channel,
                                    "text": text, "subject": subj, "attach_from": src})
