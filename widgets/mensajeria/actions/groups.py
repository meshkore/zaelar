"""Messaging actions that change HOW the card behaves or what it holds: create_group, hide/unhide, the
notification policy, the email signature and how long media stays on the device.

Every module-level name of `data` is read through it (`_d.<name>`), so a patch on `data` still governs every call.
"""
from __future__ import annotations

from .. import data as _d


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
    from .. import media as _media
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


# The EMAIL SIGNATURE (V2-611): only the config; the connector appends it once at real send time
# (`_drain_replies`). One more field on the same `config/connectors.py` "email" entry the connect wizard writes.
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
    # RAW positional read, never `connectors.email.config.signature_lines()`: that reader drops blank lines, so
    # addressing "line N" would collapse a blank middle line and the next dictated line would overwrite the wrong one.
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


# Per-connector NOTIFICATION POLICY (V2-532): which messages surface proactively (never|direct|important|all) and
# whether a surfaced batch may be SPOKEN («Telegram solo mensajes directos»; muting a group is `hide`). The logic
# lives once in `.policy`, the same one notify.surface consults.
def _a_set_notify(action, payload) -> dict:
    platform = payload.get("platform")
    if platform not in _d._PLATFORMS:
        return {"ok": False, "error": f"platform must be one of {_d._PLATFORMS}"}
    from ..policy import set_policy
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
