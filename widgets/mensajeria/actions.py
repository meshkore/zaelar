"""What each messaging action does, one function per action; `data.ACTIONS` maps the names to them (V2-778
F1-12, 2026-10-01).

Moved out of `widgets/mensajeria/data.py`'s `apply_action` if-chain with no behaviour change: each body is the branch
it was, and every module-level name of `data` it reads is read through it (`_d.<name>`), so a patch on `data`
still governs every call.
"""
from __future__ import annotations

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


# THE AUTORESPONDER (V2-624 — the INI-014 «Phase 4» go-ahead). Config only: the decision runs in
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


# V2-611 — DRAFT then SEND, as a pair: dictating a reply (or typing it) fills a visible box the operator
# can read before anything goes out; `send_draft` is the separate, deliberate act that actually sends —
# by the widget's own button or by a later voice order («envíalo»). `reply` above still exists for a
# one-shot model-dictated reply (CONFIRM-gated, unchanged) — this is the review-first path instead.
def _a_draft(action, payload) -> dict:
    db = _d.load_db()
    target = _d._outbound.resolve_reply_target(db, payload.get("n"), payload.get("messageId"))
    if target is None:
        return {"ok": False, "error": "no_target",
                 "message": "No sé a qué conversación o mensaje se refiere el borrador."}
    out = _d._drafts.write(db, target, str(payload.get("text") or ""), bool(payload.get("reply_all")))
    _d.store.save(_d.WIDGET_ID, db)
    return out


def _a_send_draft(action, payload) -> dict:
    db = _d.load_db()
    # A send names WHICH conversation whenever the widget's own button fires it; a bare voice «envíalo»
    # names nothing and gets the most recent draft, which is what it meant before drafts were per
    # conversation. Resolving the key from the payload's own target keeps both callers on one path.
    key = None
    if payload.get("n") is not None or payload.get("messageId"):
        t = _d._outbound.resolve_reply_target(db, payload.get("n"), payload.get("messageId"))
        if t is not None:
            key = _d._drafts.key(t)
    draft = _d._drafts.pick(db, key)
    text = str(draft.get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "no_draft", "message": "No hay ningún borrador que enviar."}
    stored = draft.get("target") or {}
    # Re-resolve against the LIVE item, so a target that changed since the draft was written (answered
    # elsewhere, read from the real app) is not blindly replied to under a stale identity — same
    # resolution `reply` itself uses. Falls back to the stored identity when nothing live matches: the
    # conversation's own platform/chatId are still enough to send to, even with no pending item left.
    target = _d._outbound.resolve_reply_target(db, stored.get("n"), stored.get("messageId")) or stored
    cc = _d._drafts.cc_for(draft)
    _d._outbound.enqueue_reply(db, target, text, cc=cc)
    _d._drafts.forget(db, draft.get("key") or key)
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, "to": target.get("senderId") or target.get("chatId"), "text": text,
            "cc": list(cc)}


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
        if t.get("platform") != "email":
            return {"ok": False, "error": "attachments_need_email",
                    "message": "Solo sé enviar adjuntos por correo — dime su dirección de email."}
    # A chat message is written on screen before it leaves (`_composing`); an email is a document, not a
    # line typed into a conversation, and goes straight out.
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
    return _d.apply_action("send_to", {"contact": payload.get("contact") or payload.get("to"), "channel": "email",
                                    "text": text, "subject": subj, "attach_from": src})


def _a_unread(action, payload) -> dict:
    # Back to UNREAD in his real app (email today): the message he points at, or the one open. The rule the
    # operator set for rehearsals: never archive what the demo opened — leave it unread for the next run.
    db = _d.load_db()
    m = _d._outbound._message_ref(db, payload)
    if not m or not m.get("messageId"):
        return {"ok": False, "error": "no_message", "message": "Dime qué mensaje dejo sin leer."}
    db.setdefault("pending_unread", []).append(_d._key(m))
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
        # (invoice+statements@inworld.ai), so no chat matched and the turn needed a second try. A name that shares
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
