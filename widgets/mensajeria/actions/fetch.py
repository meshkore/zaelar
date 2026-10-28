"""Messaging actions that ask the CONNECTOR or read without changing the screen: fetch_now, the autoresponder,
search_archive, peek, unread and archive/trash in the real mailbox.

Every module-level name of `data` is read through it (`_d.<name>`), so a patch on `data` still governs every call.
"""
from __future__ import annotations

from .. import data as _d


# PULL through the connector on demand (V2-624): a platform-wide fetch the connector serves against its real
# source; what arrives lands in the CONVERSATIONS as scrollback, never in triage (the past interrupts nobody).
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


# THE AUTORESPONDER (V2-624). Config only: the decision runs in
# autorespond.py at the owner's ingest, the send travels the same reply seam a dictated reply uses.
def _a_set_autoresponder(action, payload) -> dict:
    from .. import autorespond
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
    from .. import autorespond
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


# ARCHIVE / DELETE in the REAL mailbox (V2-543; email only). Same `n` addressing as read/dismiss. The item leaves
# the widget AND the order travels to the connector: archiving only here would make the widget lie about the inbox.
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
