"""Messaging actions that move the SCREEN: which list or lens is shown, which conversation is open, and asking
the app for more of it (show_view, open, close, load_more, chats_more, readchat).

Every module-level name of `data` is read through it (`_d.<name>`), so a patch on `data` still governs every call.
"""
from __future__ import annotations

from .. import chatlist as _cl
from .. import data as _d


# CHANGE WHAT IS SHOWN and ANSWER (V2-543): «vuelve a la lista principal» / «muéstrame solo el WhatsApp» are THIS
# action — re-showing the widget changes nothing. Returns the matching chats so the turn answers with names.
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
        from .. import mailbox as _mbx
        _mbx.section(db)
    # The per-platform view CRITERION (V2-624): `window_h` present sets it (0/negative clears); absent KEEPS the
    # previous one — per-platform state that persists and stays VISIBLE on the lens (a chip with a ✕).
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


# Open/close a chat thread: pure navigation by click or voice (N = the CHAT `n`; see _group_chats), or by NAME
# (V2-543): containment over accent-stripped forms, both ways.
def _a_open(action, payload) -> dict:
    n, name = _d._open_ref(payload)
    db = _d.load_db()
    # «open it» right after an archive search is the mail it found, not the inbox's first row.
    _lf = _d.last_found(db)
    if _lf and n is None and not name and payload.get("chatId") is None:
        payload = {**payload, "platform": _lf["platform"], "chatId": _lf["chatId"]}
    # V2-624 — a DIRECT identity (platform + chatId), the address an activity-view row carries. Only a
    # conversation we actually hold: opening an arbitrary identity would paint an empty thread.
    if payload.get("platform") and payload.get("chatId") is not None and n is None and not name:
        from .. import thread as _th
        key_ = (payload.get("platform"), payload.get("chatId"))
        if _th.window(db, *key_) or any(
                (it.get("platform"), str(it.get("chatId"))) == (key_[0], str(key_[1]))
                for it in db.get("items", [])):
            db["active_chat"] = {"platform": key_[0], "chatId": key_[1]}
            # Opening IS reading, locally only: the thread-store flags flip (the activity lens dot reads them);
            # nothing goes to pending_read — marking read in the real app stays an explicit `read`.
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
        # A name sharing a word with what the archive last found means that mail (its thread is named by an
        # address, so no chat name matches).
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
        from .. import thread as _th
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
