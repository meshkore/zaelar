"""What each messaging action does, one function per action; `data.ACTIONS` maps the names to them (V2-778
F1-12, 2026-10-01).

Moved out of `widgets/mensajeria/data.py`'s `apply_action` if-chain with no behaviour change: each body is the branch
it was, and every module-level name of `data` it reads is read through it (`_d.<name>`), so a patch on `data`
still governs every call.
"""
from __future__ import annotations

from . import chatlist as _cl
from . import data as _d


# CHANGE WHAT IS SHOWN and ANSWER (V2-543). «Vuelve a la lista principal» / «muéstrame solo el WhatsApp»
# are THIS action — re-showing the widget changes nothing (measured live 2026-09-01: two such orders got a
# bare show_widget and «Aquí lo tienes» over an unmoved screen). Returns the matching chats so the turn can
# answer with names instead of promising.
def _a_show_view(action, payload) -> dict:
    raw = str(payload.get("platform") or payload.get("view") or "").strip().lower()
    if raw not in _d._PLAT_ALIASES:
        return {"ok": False,
                "error": "no reconozco esa vista — vuelve a llamar a show_view con `platform`: 'all' "
                         "(la lista principal unificada), 'whatsapp', 'telegram' o 'email'"}
    platform = _d._PLAT_ALIASES[raw]
    db = _d.load_db()
    db["active_chat"] = None            # every list view exits an open thread ("volver" included)
    if platform == "email":             # the mail section opens on its folder's list, never on a stale message
        from . import mailbox as _mbx
        _mbx.section(db)
    # V2-624 — the per-platform view CRITERION («todas las conversaciones con actividad en las últimas 72
    # horas»). `window_h` present = set it (0/negative clears, back to the classic pending view); absent =
    # KEEP whatever he set before — the criterion is per-platform STATE, his words, not per-utterance. It
    # persists until changed and stays VISIBLE on the lens (a chip with a ✕), never a silent mode.
    if platform and "window_h" in payload:
        try:
            win = float(payload.get("window_h") or 0)
        except (TypeError, ValueError):
            return {"ok": False,
                    "error": "window_h tiene que ser un número de HORAS (72 = últimos 3 días); "
                             "0 quita el criterio y vuelve a la vista de pendientes"}
        crit = db.setdefault("lens_criteria", {})
        if win > 0:
            crit[platform] = {"window_h": min(win, _d._WINDOW_MAX_H)}
        else:
            crit.pop(platform, None)
    _d._push_view(db, platform)
    # Entering WhatsApp or Telegram shows its chat list; the first page is (re)asked from the connector here,
    # so the voice and the header icon both get it.
    _cl.ask(db, platform)
    _d.store.save(_d.WIDGET_ID, db)
    out = _d.view_data()
    chats = [c for c in out.get("chats", []) if not platform or c.get("platform") == platform]
    result = {"platform": platform or "all", "count": len(chats),
              "chats": [{"n": c.get("n"), "name": c.get("name"), "platform": c.get("platform"),
                         "count": c.get("count")} for c in chats[:12]]}
    result.update(_d._activity_answer(_d.load_db(), platform))
    return {"ok": True, "result": result, **out}


# PULL through the connector, on demand (V2-624 — the operator's «¿puedes ir al conector y chupar más
# mensajes?», refused honestly on 2026-09-08 because no such door existed). Enqueues a platform-wide
# fetch the connector serves against its real source; what arrives lands in the CONVERSATIONS as
# scrollback (never in triage — pulling the past must not interrupt anybody).
def _a_fetch_now(action, payload) -> dict:
    raw = str(payload.get("platform") or "").strip().lower()
    platform = _d._PLAT_ALIASES.get(raw, raw)
    if platform not in _d._FETCH_PLATFORMS:
        if platform == "whatsapp":
            return {"ok": False,
                    "error": ("WhatsApp no permite pedirle al teléfono las conversaciones en bloque: lo "
                              "nuevo llega solo en tiempo real, y de un chat CONCRETO que ya tengamos sí "
                              "puedo traer mensajes anteriores (open + load_more)")}
        return {"ok": False,
                "error": "fetch_now necesita `platform`: 'telegram' o 'email' (WhatsApp no soporta la "
                         "traída en bloque; ver su propio error)"}
    try:
        since = float(payload.get("since_hours") or _d._FETCH_DEFAULT_H)
    except (TypeError, ValueError):
        since = _d._FETCH_DEFAULT_H
    since = max(1.0, min(since, _d._WINDOW_MAX_H))
    db = _d.load_db()
    db.setdefault("pending_fetch", []).append({"platform": platform, "since_hours": since})
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True,
            "result": {"asked": True, "platform": platform, "since_hours": since,
                       "detail": "se lo he pedido al conector; las conversaciones de ese período irán "
                                 "apareciendo en unos segundos"},
            **_d.view_data()}


# THE AUTORESPONDER (V2-624 — the «Phase 4» go-ahead). Config only: the decision runs in
# autorespond.py at the owner's ingest, the send travels the same reply seam a dictated reply uses.
def _a_set_autoresponder(action, payload) -> dict:
    from . import autorespond
    raw = str(payload.get("platform") or "all").strip().lower()
    plats = list(_d._PLATFORMS) if raw in ("all", "todas", "todos", "") else [_d._PLAT_ALIASES.get(raw, raw)]
    if any(p not in _d._PLATFORMS for p in plats):
        return {"ok": False,
                "error": "set_autoresponder necesita `platform`: 'whatsapp', 'telegram', 'email' o 'all'"}
    text = payload.get("text")
    enabled = payload.get("enabled")
    db = _d.load_db()
    if enabled and not str(text or "").strip() and \
            not any(autorespond.config_for(db, p)["text"] for p in plats):
        return {"ok": False,
                "error": "no hay ningún mensaje que responder — pásame `text` con lo que debe contestar"}
    try:
        for p in plats:
            autorespond.set_config(db, p, text=text, hours=payload.get("hours"), enabled=enabled)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, "result": {"autoresponder": _d._autoresponder_view(db)}, **_d.view_data()}


def _a_clear_autoresponder(action, payload) -> dict:
    from . import autorespond
    raw = str(payload.get("platform") or "all").strip().lower()
    plats = list(_d._PLATFORMS) if raw in ("all", "todas", "todos", "") else [_d._PLAT_ALIASES.get(raw, raw)]
    db = _d.load_db()
    for p in plats:
        if p in _d._PLATFORMS:
            autorespond.clear_config(db, p)
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, "result": {"autoresponder": _d._autoresponder_view(db)}, **_d.view_data()}


# `peek` (V2-624), `search_archive` and `chat_digest` (V2-628) are ANSWER-ONLY: answer_action returns the conversation's content and nothing here has
# anything to mutate. Falling through to the generic branch would re-save the store for a read.
def _a_search_archive(action, payload) -> dict:
    _d._bring_back_found_mail(payload)
    _d._remember_found(payload)
    return _d.view_data()


def _a_peek(action, payload) -> dict:
    return _d.view_data()


# Reply to a message (V2-051): enqueue into pending_reply so that platform's connector sends it. `n` follows
# the same duality as read/dismiss: with an open chat it is a message `n` from items; with the chat list it is
# a chat `n` pointing to its last message. The connector performs the real send; the CONFIRM gate (V2-025)
# already asked for OK before reaching this branch.
def _a_reply(action, payload) -> dict:
    # UNCHANGED contract (V2-521, tested): `n` means an item in the open thread, or a CHAT in the chat
    # list otherwise — the same duality `hide` documents. `draft`/`send_draft` below are the new,
    # unambiguous path (`n`/`messageId` address one ITEM directly, matching archive/trash's own meaning
    # of `n` for the flat email list); `reply` keeps its original resolution so nothing that already
    # depends on it — voice included — changes behavior.
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
        # A reply with nothing to answer is a send that did not happen, and it must SAY so (use case
        # dictate-a-reply-honestly, 2026-10-15: «respóndele a Marta por WhatsApp…» with no chat of hers and WhatsApp
        # unlinked came back as the card's whole state, and the turn said «Hecho.»). What leaves the machine is
        # never claimed without the act — the operator's rule for anything that reaches somebody else.
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


# V2-611 — DRAFT then SEND, as a pair: dictating a reply (or typing it) fills a visible box the operator
# can read before anything goes out; `send_draft` is the separate, deliberate act that actually sends —
# by the widget's own button or by a later voice order («envíalo»). `reply` above still exists for a
# one-shot model-dictated reply (CONFIRM-gated, unchanged) — this is the review-first path instead.
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
    from . import card_send as _card
    if _card.is_card_send(payload):     # V2-819: the card's own Send — its text, its conversation, answered
        return _card.send(payload)
    db = _d.load_db()
    # A send names WHICH conversation whenever the widget's own button fires it; a bare voice «envíalo»
    # names nothing and gets the most recent draft, which is what it meant before drafts were per
    # conversation. Resolving the key from the payload's own target keeps both callers on one path.
    # V2-800: a held NEW message is named by its recipient (`contact`), and `at`/`in_minutes` schedule it.
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
    # Re-resolve against the LIVE item, so a target that changed since the draft was written (answered
    # elsewhere, read from the real app) is not blindly replied to under a stale identity — same
    # resolution `reply` itself uses. Falls back to the stored identity when nothing live matches: the
    # conversation's own platform/chatId are still enough to send to, even with no pending item left.
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
    # V2-683 — writing to a PERSON who has not written to us. WHO and by WHICH channel are resolved in
    # `outbound.py` (which asks `widgets/directory.py`), and an unresolved one comes back as a refusal
    # that says what is missing: this door can say the right thing to the WRONG person, and that is the
    # one mistake it cannot take back.
    db = _d.load_db()
    t = _d._outbound.resolve_target(payload)
    if not t.get("ok"):
        return t
    # FORWARDING what arrived (the operator's demo, 2026-09-28: «open the Inworld invoice and send the invoice
    # to Quinn»): `attach_from` points at a message on the card — its `n`, its `messageId`, or `{}` for the
    # one open — and its files travel with this send. Asked for and absent is a refusal, never a mail that
    # announces an attachment it does not carry.
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
        # Demo pass 127, E3: the verdict's forward went out and the same-turn correction of the model's refused
        # forward sent the receipt to Quinn a SECOND time. The same files to the same person seconds later are
        # one send; it is reported as done, never queued again.
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
    # FORWARD = a send to a person carrying the files of a message that arrived (the operator's demo: «send the
    # invoice to Quinn»). One name for what he asks, instead of a parameter the model has to remember — measured
    # 2026-09-28: the model reached for `reply` (to the SENDER of the invoice) and the files never travelled.
    src = {k: payload[k] for k in ("n", "messageId", "from") if payload.get(k) not in (None, "")}
    db0 = _d.load_db()
    orig = _d._outbound._message_ref(db0, src) or {}
    subj = str(payload.get("subject") or "").strip() or (f"Fwd: {orig.get('subject')}" if orig.get("subject") else "Fwd")
    text = str(payload.get("text") or "").strip() or subj
    # The channel is the one he names («por WhatsApp»); mail when he names none, as it always was.
    channel = str(payload.get("channel") or payload.get("platform") or "email").strip().lower()
    return _d.apply_action("send_to", {"contact": payload.get("contact") or payload.get("to"), "channel": channel,
                                    "text": text, "subject": subj, "attach_from": src})


def _a_unread(action, payload) -> dict:
    # Back to UNREAD in his real app (email today): the message he points at, or the one open. The rule the
    # operator set for rehearsals: never archive what the demo opened — leave it unread for the next run.
    db = _d.load_db()
    m = _d._outbound._message_ref(db, payload)
    if not m or not m.get("messageId"):
        return {"ok": False, "error": "no_message", "message": "Dime qué mensaje dejo sin leer."}
    # The message's time anchors WhatsApp's «mark as unread»; only carried when there is one.
    db.setdefault("pending_unread", []).append({**_d._key(m), **({"ts": m["ts"]} if m.get("ts") else {})})
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, "result": {"unread": 1, "from": m.get("from") or m.get("who") or "",
                                   "subject": m.get("subject") or ""}}


# V2-611 — the EMAIL SIGNATURE, appended once by the connector at real send time (service.py's
# `_drain_replies`), never here: this only writes the config the connector reads. `config/connectors.py`
# is the SAME store the connect wizard already writes to for email — signature_lines is one more field
# on the same "email" entry, not a new mechanism.
def _a_set_signature(action, payload) -> dict:
    lines = payload.get("lines")
    if not isinstance(lines, list):
        return {"ok": False, "error": "bad_lines", "message": "Dame las líneas de la firma."}
    lines = [str(x).strip()[:200] for x in lines[:10]]
    while lines and not lines[-1]:
        lines.pop()
    from config import connectors as _conn_store
    _conn_store.set("email", {"signature_lines": lines})
    return {"ok": True, "lines": lines}


def _a_set_signature_line(action, payload) -> dict:
    try:
        i = int(payload.get("line"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_line", "message": "Dime qué número de línea (1, 2, 3…)."}
    if not 1 <= i <= 10:
        return {"ok": False, "error": "bad_line", "message": "La firma admite hasta 10 líneas."}
    text = str(payload.get("text") or "").strip()[:200]
    from config import connectors as _conn_store
    # RAW positional read, never `connectors.email.config.signature_lines()` — that reader FILTERS
    # blank lines for the sender (a trailing/leading blank in the actual email is cosmetic noise there),
    # which is exactly wrong for addressing "line N" by index here: filtering first would silently
    # collapse an already-set blank middle line and the NEXT dictated line would overwrite the wrong
    # one (found live, verifying this feature — line 1 + line 3 read back as two lines, not three).
    raw = _conn_store.get("email").get("signature_lines")
    lines = [str(x) for x in raw] if isinstance(raw, list) else []
    while len(lines) < i:
        lines.append("")
    lines[i - 1] = text
    while lines and not lines[-1]:
        lines.pop()
    _conn_store.set("email", {"signature_lines": lines})
    return {"ok": True, "line": i, "lines": lines}


def _a_clear_signature(action, payload) -> dict:
    from config import connectors as _conn_store
    _conn_store.set("email", {"signature_lines": []})
    return {"ok": True, "lines": []}


# Mute channel: N addresses the same way as read/dismiss depending on context. With an open chat it is a
# message `n` from `items`; with the chat list it is a chat `n` from `_group_chats`. Same duality already
# documented in brief.py for read/dismiss/hide.
def _a_hide(action, payload) -> dict:
    n = payload.get("n")
    if n is not None:
        db = _d.load_db()
        platform = chat_id = group = None
        if db.get("active_chat") is not None:
            for it in _d._renumber(db.get("items", [])):
                if it.get("n") == n:
                    platform, chat_id = it.get("platform"), it.get("chatId")
                    group = it.get("group") or it.get("from") or ""
                    break
        else:
            match = next((c for c in _d._group_chats(_d._visible_items(db)) if c.get("n") == n), None)
            if match:
                platform, chat_id, group = match["platform"], match["chatId"], match["name"]
        if platform and chat_id is not None:
            key = (platform, str(chat_id))
            muted = db.get("muted_channels", [])
            if not any((m.get("platform"), str(m.get("chatId"))) == key for m in muted):
                muted.append({"platform": platform, "chatId": chat_id, "group": group})
                db["muted_channels"] = muted
            db["items"] = [it for it in db.get("items", [])
                           if (it.get("platform"), str(it.get("chatId"))) != key]
            _d.store.save(_d.WIDGET_ID, db)
    return _d.view_data()


# Per-connector NOTIFICATION POLICY (V2-532): how a channel may interrupt — which messages surface
# proactively (never|direct|important|all) and whether a surfaced batch may be SPOKEN. Voice-settable
# («no me avises de los grupos de Telegram» is `hide`; «Telegram solo mensajes directos» is this). The
# decision logic lives in `.policy` (zero-import module) and is the same one notify.surface consults —
# one rule, two readers, never two copies.
def _a_set_notify(action, payload) -> dict:
    platform = payload.get("platform")
    if platform not in _d._PLATFORMS:
        return {"ok": False, "error": f"platform must be one of {_d._PLATFORMS}"}
    from .policy import set_policy
    db = _d.load_db()
    try:
        pol = set_policy(db, platform, notify=payload.get("notify"), speak=payload.get("speak"),
                         highlight=payload.get("highlight"))
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, "platform": platform, "policy": pol, **_d.view_data()}


def _a_unhide(action, payload) -> dict:
    platform = payload.get("platform")
    chat_id = payload.get("chatId")
    if platform and chat_id is not None:
        db = _d.load_db()
        key = (platform, str(chat_id))
        db["muted_channels"] = [m for m in db.get("muted_channels", [])
                                 if (m.get("platform"), str(m.get("chatId"))) != key]
        _d.store.save(_d.WIDGET_ID, db)
    return _d.view_data()


# Open/close a chat thread: pure navigation, addressable by click or voice
# ([[msg.open:N]]/[[msg.close]], N = the CHAT `n`; see _group_chats). V2-543: also by NAME — the operator
# says «abre el chat de Jose Vicente», not a number; containment over accent-stripped forms, both ways.
def _a_open(action, payload) -> dict:
    n, name = _d._open_ref(payload)
    db = _d.load_db()
    # Demo pass 62, E2 — «open it» right after an archive search is the mail it found, not the inbox's first row.
    _lf = _d.last_found(db)
    if _lf and n is None and not name and payload.get("chatId") is None:
        payload = {**payload, "platform": _lf["platform"], "chatId": _lf["chatId"]}
    # V2-624 — a DIRECT identity (platform + chatId), the address an activity-view row carries. Only a
    # conversation we actually hold: opening an arbitrary identity would paint an empty thread.
    if payload.get("platform") and payload.get("chatId") is not None and n is None and not name:
        from . import thread as _th
        key_ = (payload.get("platform"), payload.get("chatId"))
        if _th.window(db, *key_) or any(
                (it.get("platform"), str(it.get("chatId"))) == (key_[0], str(key_[1]))
                for it in db.get("items", [])):
            db["active_chat"] = {"platform": key_[0], "chatId": key_[1]}
            # Opening IS reading, locally: he sees the whole conversation on screen, so the
            # thread-store flags flip here (the activity lens dot reads them). Local ONLY —
            # nothing is enqueued to pending_read: marking read in the real app stays an
            # explicit `read`, never a side effect of navigating.
            _th.mark_read(db, key_[0], key_[1])
            _d.store.save(_d.WIDGET_ID, db)
            return _d.view_data()
        listed = _cl.row(db, *key_)
        if listed is not None:
            # A chat from the CHAT LIST that this widget holds nothing of yet: open it and ask the app for its
            # latest messages. The thread is created with the list's name, so the screen is labelled while
            # they arrive, and `opening` keeps it from auto-closing as empty in the meantime.
            th = _th._thread(db, *key_)
            th["name"] = th.get("name") or listed.get("name") or ""
            if listed.get("kind") == "group":
                th["isGroup"] = True
            db["active_chat"] = {"platform": key_[0], "chatId": key_[1]}
            db["opening"] = {"key": _th.key(*key_), "at": _d.time.time()}
            if key_[0] in _d._HISTORY_PLATFORMS:
                db.setdefault("pending_history", []).append({
                    "platform": key_[0], "chatId": key_[1], "limit": _d._HISTORY_LIMIT,
                    "beforeTs": float(listed.get("ts") or 0) + 1, "beforeId": listed.get("lastId") or "",
                    "beforeFromMe": bool(listed.get("fromMe")), "includeAnchor": True,
                })
            _d.store.save(_d.WIDGET_ID, db)
            return _d.view_data()
        return {"ok": False, "error": "no tengo esa conversación guardada", **_d.view_data()}
    chats = _d._group_chats(_d._visible_items(db))
    match = None
    if n is not None:
        # `n` addresses the LIST on screen and nothing else — a number has no meaning for a conversation
        # that is not in it, and guessing one would open the wrong chat.
        match = next((c for c in chats if c.get("n") == n), None)
    elif name:
        match = _d._find_chat_by_name(db, name)
        # Demo pass 66, E2: «open it» came as open {name: "Inworld invoice"} — the thread is named by its address
        # (a vendor's invoice address), so no chat matched and the turn needed a second try. A name that shares
        # a word with what the archive last found means that mail.
        if match is None and _lf:
            import re as _re
            said = {w for w in _re.findall(r"[a-z0-9]{4,}", name.lower())}
            known = set(_re.findall(r"[a-z0-9]{4,}", " ".join(str(_lf.get(k) or "") for k in ("name", "chatId", "subject")).lower()))
            if said & known:
                match = {"platform": _lf["platform"], "chatId": _lf["chatId"]}
    if match is None and (n is not None or name):
        return {"ok": False,
                "error": "no encuentro ese chat — vuelve a llamar a open con el `n` de la lista o con "
                         "`name` tal como aparece en ella",
                **_d.view_data()}
    if match:
        db["active_chat"] = {"platform": match["platform"], "chatId": match["chatId"]}
        # Same as the identity branch above: opening is reading, locally only.
        from . import thread as _th
        _th.mark_read(db, match["platform"], match["chatId"])
        _d.store.save(_d.WIDGET_ID, db)
    return _d.view_data()


def _a_close(action, payload) -> dict:
    db = _d.load_db()
    if db.get("active_chat") is not None:
        db["active_chat"] = None
        _d.store.save(_d.WIDGET_ID, db)
    return _d.view_data()


# LOAD PREVIOUS messages of the open conversation (V2-546) — by button or by voice («tráeme los anteriores»).
# Enqueues an order the platform's connector fulfils against its real source; nothing is fabricated here.
def _a_load_more(action, payload) -> dict:
    db = _d.load_db()
    chat = db.get("active_chat")
    if payload.get("platform") and payload.get("chatId") is not None:
        chat = {"platform": payload.get("platform"), "chatId": payload.get("chatId")}
    if not chat:
        return {"ok": False,
                "error": "no hay ninguna conversación abierta — abre primero el chat con open y vuelve a "
                         "llamar a load_more",
                **_d.view_data()}
    platform = chat.get("platform")
    if platform not in _d._HISTORY_PLATFORMS:
        return {"ok": False,
                "error": f"traer mensajes anteriores no está soportado para {platform} todavía",
                **_d.view_data()}
    info = _d._thread_meta(db, chat) or {}
    if info.get("complete"):
        return {"ok": True, "result": {"loaded": 0, "complete": True,
                                       "detail": "ya tienes el principio de esta conversación"},
                **_d.view_data()}
    try:
        limit = max(1, min(100, int(payload.get("limit") or _d._HISTORY_LIMIT)))
    except (TypeError, ValueError):
        limit = _d._HISTORY_LIMIT
    db.setdefault("pending_history", []).append({
        "platform": platform, "chatId": chat.get("chatId"),
        "beforeTs": info.get("oldest_ts") or 0, "beforeId": info.get("oldest_id") or "",
        "limit": limit,
    })
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True,
            "result": {"asked": limit, "platform": platform,
                       "detail": "se los he pedido a la app; aparecerán arriba en cuanto lleguen"},
            **_d.view_data()}


# CREATE A GROUP («crea un grupo con Ana y Luis que se llame Viaje»). Every member resolves through the same
# door a send does — one unresolved or ambiguous person and nothing is created, with the reason: a group with
# the wrong person in it is a message to the wrong person.
_GROUP_PLATFORMS = ("whatsapp", "telegram")


def _a_create_group(action, payload) -> dict:
    raw = str(payload.get("platform") or payload.get("channel") or "").strip().lower()
    platform = _d._PLAT_ALIASES.get(raw, raw)
    name = str(payload.get("name") or payload.get("title") or "").strip()
    members = payload.get("members") or payload.get("contacts") or []
    if isinstance(members, str):
        members = [m.strip() for m in members.replace(" y ", ",").replace(" and ", ",").split(",") if m.strip()]
    if platform not in _GROUP_PLATFORMS:
        return {"ok": False, "error": "create_group necesita `platform`: 'whatsapp' o 'telegram'"}
    if not name or not members:
        return {"ok": False, "error": "create_group necesita `name` (cómo se llama el grupo) y `members` "
                                      "(los nombres de las personas)"}
    resolved, problems = [], []
    for who in members[:50]:
        t = _d._outbound.resolve_target({"contact": who, "channel": platform, "text": "·"})
        if t.get("ok"):
            resolved.append({"to": t.get("to"), "chatId": t.get("chatId"), "name": t.get("name"),
                             "contactId": t.get("contactId") or ""})
        else:
            problems.append(f"{who}: {t.get('error')}")
    if problems:
        return {"ok": False, "error": "no creo el grupo hasta tener a todos: " + " | ".join(problems)}
    db = _d.load_db()
    files = _d._media.local_paths(_d.store.data_dir(_d.WIDGET_ID), payload.get("files"))
    order = {"platform": platform, "ref": _d._outbound.new_ref(), "name": name, "members": resolved,
             "text": str(payload.get("text") or "").strip(), "attachments": files}
    db.setdefault("pending_group", []).append(order)
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, "result": {"platform": platform, "name": name, "members": [m["name"] for m in resolved],
                                   "ref": order["ref"], "detail": "pedido a la app; aparecerá en la lista de chats"},
            **_d.view_data()}


# How long downloaded media stays on this device (media.py): «guarda las fotos 30 días», or Ajustes.
def _a_set_media_days(action, payload) -> dict:
    from . import media as _media
    db = _d.load_db()
    raw = payload.get("days")
    if str(raw).strip().lower() in ("siempre", "always", "forever", "never"):
        raw = 0
    d = _media.set_days(db, raw)
    if d is None:
        return {"ok": False,
                "error": "days tiene que ser 7, 14, 30, 90 o 0 (0 = guardar siempre)", **_d.view_data()}
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, "result": {"media_days": d}, **_d.view_data()}


# «Cargar más» at the bottom of a platform's chat list (button or voice: «enséñame más chats de WhatsApp»).
def _a_chats_more(action, payload) -> dict:
    db = _d.load_db()
    raw = str(payload.get("platform") or (db.get("view") or {}).get("platform") or "").strip().lower()
    platform = _d._PLAT_ALIASES.get(raw, raw)
    if platform not in _cl.LIST_PLATFORMS:
        return {"ok": False,
                "error": "la lista de chats existe para 'whatsapp' y 'telegram' — vuelve a llamar a chats_more "
                         "con `platform`",
                **_d.view_data()}
    res = _cl.more(db, platform)
    _d.store.save(_d.WIDGET_ID, db)
    out = _d.view_data()
    rows = (out.get("chat_list") or {}).get(platform, {}).get("rows") or []
    return {"ok": True, "result": {**res, "platform": platform,
                                   "chats": [{"name": r.get("name"), "kind": r.get("kind"),
                                              "unread": r.get("unread")} for r in rows[-_cl.PAGE:]]},
            **out}


# Mark an entire chat read without opening it (voice: [[msg.readchat:N]], N = the CHAT `n`).
def _a_readchat(action, payload) -> dict:
    n = payload.get("n")
    if n is not None:
        db = _d.load_db()
        match = next((c for c in _d._group_chats(_d._visible_items(db)) if c.get("n") == n), None)
        if match:
            key = (match["platform"], str(match["chatId"]))
            pending = db.get("pending_read", [])
            keep = []
            for it in db.get("items", []):
                if (it.get("platform"), str(it.get("chatId"))) == key:
                    pending.append(_d._key(it))
                else:
                    keep.append(it)
            db["items"] = keep
            db["pending_read"] = pending
            _d.store.save(_d.WIDGET_ID, db)
    return _d.view_data()


# ARCHIVE / DELETE in the REAL mailbox (V2-543; email only today). Same `n` addressing as read/dismiss.
# The item leaves the widget AND the order travels to the platform's connector: archiving here without
# archiving there would make the widget a lie about the real inbox — the whole point is not having to
# open the real app afterwards.
def _a_archive(action, payload) -> dict:
    n = payload.get("n")
    mid = payload.get("messageId")
    db = _d.load_db()
    items = _d._renumber(db.get("items", []))
    hit = next((it for it in items
                if (n is not None and it.get("n") == n) or (mid and it.get("messageId") == mid)), None)
    if hit is None:
        return {"ok": False,
                "error": f"no encuentro ese mensaje — vuelve a llamar a {action} con el `n` de la lista",
                **_d.view_data()}
    if hit.get("platform") != "email":
        return {"ok": False,
                "error": ("archivar/borrar en la app real solo está soportado para EMAIL hoy — para "
                          "WhatsApp/Telegram usa read (marcar leído) o dismiss (descartar del widget)"),
                **_d.view_data()}
    db.setdefault(f"pending_{action}", []).append(_d._key(hit))
    db["items"] = [it for it in db.get("items", []) if it is not hit]
    _d.store.save(_d.WIDGET_ID, db)
    verb = "archivado" if action == "archive" else "enviado a borrar"
    return {"ok": True, "result": {"action": action, "from": hit.get("from"),
                                   "subject": hit.get("subject", ""), "detail": verb},
            **_d.view_data()}
