#
# Messaging widget data layer (INI-015). Reads/mutates the unified store (widgets/_data/mensajeria.json), written
# by connector engines (connectors/whatsapp/service.py and connectors/telegram/service.py through
# connectors/messaging/store.py). The widget is the face; connectors are the engines. One list for all platforms.
#
# Widget contract: data.py is stdlib-only plus the `widgets` package for isolation, so it does NOT import
# `connectors`. It uses `widgets.store` directly on the same file/id as the connector. view_data never raises. The
# operator's actions enqueue the key, including `platform`, into `pending_read`; the correct connector drains it and
# marks the message read in its app. A platform failure does not bring down another platform or voice.
#
import time
import unicodedata

from .. import store

WIDGET_ID = "mensajeria"
_PLATFORMS = ("whatsapp", "telegram", "email")   # email: V2-051
_URG_RANK = {"alta": 0, "media": 1, "baja": 2}   # local copy; data.py is stdlib-only and does not import connectors

# ── The VIEW is a declared ACTION (V2-543 — the V2-540/V2-541 lesson applied here) ──────────────────────────────
# The platform lens used to be widget.js-local state the voice could not touch, and "back to the main list" had no
# action at all: measured live (2026-09-01 18:39), «ve a la lista principal de los mensajes» could only re-show the
# widget, which changes nothing. The requested view is pushed with a MONOTONIC witness counter (`n`) so asking for
# the same view twice still lands (the token moves even when the value repeats), and it EXPIRES server-side: a
# pushed lens kept forever would yank next week's reopen back to a stale filter.
_VIEW_TTL_S = 600
# Spoken platform names as the operator says them; "" = the unified main list. Structural aliases only — never a
# per-language synonym table beyond what names these three channels.
_PLAT_ALIASES = {
    "whatsapp": "whatsapp", "wasap": "whatsapp", "wa": "whatsapp",
    "telegram": "telegram", "tg": "telegram",
    "email": "email", "correo": "email", "mail": "email", "gmail": "email", "outlook": "email",
    "all": "", "todo": "", "todos": "", "": "", "inbox": "", "principal": "", "general": "", "lista": "",
}


def _norm_txt(s) -> str:
    """Accent-stripped lowercase, for matching a spoken chat name against the list."""
    s = unicodedata.normalize("NFD", str(s or "").strip().lower())
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def _push_view(db: dict, platform: str) -> None:
    prev = db.get("view") or {}
    db["view"] = {"platform": platform, "n": int(prev.get("n", 0) or 0) + 1, "at": time.time()}


def _fresh_view(db: dict):
    """The pushed view, or None once it has expired. Expiry costs an open widget nothing: `view` merely stops
    arriving, the client token stops moving, and whatever the operator chose by hand survives."""
    v = db.get("view")
    if not isinstance(v, dict):
        return None
    try:
        if time.time() - float(v.get("at", 0) or 0) > _VIEW_TTL_S:
            return None
    except (TypeError, ValueError):
        return None
    return v


def _empty() -> dict:
    return {
        "platforms": {p: {"status": "off", "qr": None} for p in _PLATFORMS},
        "updated": "",
        "items": [],
        "pending_read": [],
        "pending_reply": [],
        "pending_control": [],
        "active_chat": None,   # {"platform":..., "chatId":...} | None: open thread in the widget (click or voice)
    }


def blank() -> dict:
    """Blank state for an operator reset: remove messages and queues, but preserve each platform's connection
    state. The reset promises not to touch credentials or authentication, and a plain `_empty()` would leave all
    three platforms at `status:"off"`, making it look like the reset disconnected WhatsApp while the account remains
    linked. Called by `widgets/reset.py`, which prefers this function so each widget decides what "blank" means."""
    fresh = _empty()
    cur = store.load(WIDGET_ID, {})
    if isinstance(cur.get("platforms"), dict):
        fresh["platforms"] = cur["platforms"]
    return fresh


def load_db() -> dict:
    db = store.load(WIDGET_ID, _empty())
    if not isinstance(db.get("platforms"), dict):
        db["platforms"] = {}
    for p in _PLATFORMS:
        if not isinstance(db["platforms"].get(p), dict):
            db["platforms"][p] = {"status": "off", "qr": None}
    db.setdefault("items", [])
    db.setdefault("pending_read", [])
    db.setdefault("pending_reply", [])
    db.setdefault("updated", "")
    db.setdefault("active_chat", None)
    return db


def _renumber(items: list) -> list:
    for i, it in enumerate(items, 1):
        it["n"] = i
    return items


def _key(it: dict) -> dict:
    return {"platform": it.get("platform"), "chatId": it.get("chatId"),
            "messageId": it.get("messageId"), "senderId": it.get("senderId")}


def _visible_items(db: dict) -> list:
    """Non-muted, renumbered items: the same base list seen by the widget and the brain."""
    muted_channels = db.get("muted_channels", [])
    muted_keys = {(m.get("platform"), str(m.get("chatId"))) for m in muted_channels}
    return _renumber([
        it for it in db.get("items", [])
        if (it.get("platform"), str(it.get("chatId"))) not in muted_keys
    ])


def _group_chats(items: list) -> list:
    """Group the flat, already renumbered list by (platform, chatId), preserving appearance order: one item per
    chat instead of one per message. Each chat has its own `n`, a separate addressing space from `items`
    ([[msg.open:N]]/[[msg.readchat:N]] use this; [[msg.read:N]]/[[msg.dismiss:N]] still use the `items` `n`, only
    addressable when the chat is open)."""
    order, by_key = [], {}
    for it in items:
        key = (it.get("platform"), str(it.get("chatId")))
        g = by_key.get(key)
        if g is None:
            g = {"platform": it.get("platform"), "chatId": it.get("chatId"),
                 "name": it.get("group") or it.get("from") or "?", "isGroup": bool(it.get("isGroup")),
                 "count": 0, "rank": 3, "dirigido_a_mi": False, "last": it}
            by_key[key] = g
            order.append(key)
        g["count"] += 1
        g["rank"] = min(g["rank"], _URG_RANK.get(it.get("urgencia"), 3))
        g["dirigido_a_mi"] = g["dirigido_a_mi"] or bool(it.get("dirigido_a_mi"))
        g["last"] = it   # most recent by appearance order; the store has no timestamp
    rank_to_urg = {0: "alta", 1: "media", 2: "baja"}
    chats = []
    for i, key in enumerate(order, 1):
        g = by_key[key]
        last = g["last"]
        chats.append({
            "n": i, "platform": g["platform"], "chatId": g["chatId"], "name": g["name"],
            "isGroup": g["isGroup"], "count": g["count"], "dirigido_a_mi": g["dirigido_a_mi"],
            "urgencia": rank_to_urg.get(g["rank"], "media"),
            "lastFrom": last.get("from"), "lastBody": last.get("body", ""), "lastMotivo": last.get("motivo", ""),
            # V2-543: real time + media class of the preview (0/"" for legacy rows without them).
            "lastTs": last.get("ts", 0), "lastMediaType": last.get("mediaType", ""),
        })
    return chats


def _notify_policy_view(db: dict) -> dict:
    """Effective (normalized) notification policy per platform, for the card and for read_widget. Always the
    full platform set, so a reader never has to guess what an absent entry means."""
    from .policy import policy_for
    return {p: policy_for(db, p) for p in _PLATFORMS}


def view_data(q: str = "") -> dict:
    db = load_db()
    items = _visible_items(db)
    chats = _group_chats(items)
    muted_channels = db.get("muted_channels", [])

    active = db.get("active_chat")
    active_key = (active.get("platform"), str(active.get("chatId"))) if active else None
    active_items = [it for it in items if (it.get("platform"), str(it.get("chatId"))) == active_key] \
        if active_key else []
    if active and not active_items:
        # The open chat ran out of messages after all were read/dismissed. Close it automatically instead of
        # leaving an empty thread waiting for the operator to press "back", and avoid resurrecting it if a much
        # later message arrives in the same chat after the operator considered it closed.
        db["active_chat"] = None
        store.save(WIDGET_ID, db)
        active = None

    return {
        "platforms": db.get("platforms", {}),
        "updated": db.get("updated", ""),
        "items": items,
        "count": len(items),
        "chats": chats,
        "active_chat": active,
        "active_items": active_items,
        "muted_channels": [
            {"group": m.get("group") or f"{m.get('platform')}:{m.get('chatId')}",
             "platform": m.get("platform"), "chatId": m.get("chatId")}
            for m in muted_channels
        ],
        # V2-532 — the per-connector notification policy, so the card (and the brain, via read_widget) can see
        # HOW each channel is allowed to interrupt. Normalized through the policy module: the store may hold
        # partial or legacy shapes and the reader must always see the effective values.
        "notify_policy": _notify_policy_view(db),
        # V2-520 — the brain asking to CONNECT a channel. The channels panel is local widget.js state that only
        # the header button could ever flip, so "conéctame el correo" opened the card on the MESSAGES view and
        # the operator saw no form at all (measured 2026-08-31). Carried with a timestamp, not consumed on read:
        # view_data runs on every render, and clearing it here would lose the request on the first repaint.
        "connect_focus": db.get("connect_focus") or None,
        # V2-543 — the requested VIEW (platform lens / main list), witness-countered + server-expired.
        "view": _fresh_view(db),
    }


def apply_action(action: str, payload: dict | None = None) -> dict:
    """Operator actions from the widget, the only widget->backend channel; the widget cannot fetch:
    - read/dismiss/clear mutate the list; marking read enqueues into `pending_read`, drained by the connector.
    - connect/disconnect enqueue a control command into `pending_control` (platform + credentials); the server-side
      supervisor drains it and performs the real connect/disconnect (config/connectors.py + start/stop). This lets
      the user connect Telegram/WhatsApp from the UI without touching .env. data.py remains stdlib-only."""
    payload = payload or {}

    # OPEN the channels panel (V2-520). Intent only — it stores no credential and starts no connection: the
    # form does that, because a password or an OAuth round-trip is never something to conduct by voice.
    if action == "open_connectors":
        import time as _time
        platform = (payload.get("platform") or "").lower()
        if platform not in _PLATFORMS:
            platform = ""                       # unknown/absent → open the panel, expand nothing
        db = load_db()
        db["connect_focus"] = {"platform": platform, "ts": int(_time.time() * 1000)}
        store.save(WIDGET_ID, db)
        return view_data()

    # CHANGE WHAT IS SHOWN and ANSWER (V2-543). «Vuelve a la lista principal» / «muéstrame solo el WhatsApp»
    # are THIS action — re-showing the widget changes nothing (measured live 2026-09-01: two such orders got a
    # bare show_widget and «Aquí lo tienes» over an unmoved screen). Returns the matching chats so the turn can
    # answer with names instead of promising.
    if action == "show_view":
        raw = str(payload.get("platform") or payload.get("view") or "").strip().lower()
        if raw not in _PLAT_ALIASES:
            return {"ok": False,
                    "error": "no reconozco esa vista — vuelve a llamar a show_view con `platform`: 'all' "
                             "(la lista principal unificada), 'whatsapp', 'telegram' o 'email'"}
        platform = _PLAT_ALIASES[raw]
        db = load_db()
        db["active_chat"] = None            # every list view exits an open thread ("volver" included)
        _push_view(db, platform)
        store.save(WIDGET_ID, db)
        out = view_data()
        chats = [c for c in out.get("chats", []) if not platform or c.get("platform") == platform]
        return {"ok": True,
                "result": {"platform": platform or "all", "count": len(chats),
                           "chats": [{"n": c.get("n"), "name": c.get("name"), "platform": c.get("platform"),
                                      "count": c.get("count")} for c in chats[:12]]},
                **out}

    # Connection control, executed by the supervisor, not the widget.
    if action in ("connect", "disconnect"):
        platform = (payload.get("platform") or "").lower()
        if platform in _PLATFORMS:
            db = load_db()
            cmd = {"platform": platform, "cmd": action}
            if action == "connect" and platform == "telegram":
                cmd["api_id"] = str(payload.get("api_id") or "").strip()
                cmd["api_hash"] = str(payload.get("api_hash") or "").strip()
            if action == "connect" and platform == "email":
                # Credentials from the widget form (V2-051). supervisor->control.py persists them redacted.
                for k in ("email_address", "email_password", "provider",
                          "imap_host", "imap_port", "smtp_host", "smtp_port"):
                    if payload.get(k) not in (None, ""):
                        cmd[k] = payload.get(k)
            if action == "disconnect" and payload.get("forget"):
                cmd["forget"] = True
            db.setdefault("pending_control", []).append(cmd)
            store.save(WIDGET_ID, db)
        return view_data()

    # Reply to a message (V2-051): enqueue into pending_reply so that platform's connector sends it. `n` follows
    # the same duality as read/dismiss: with an open chat it is a message `n` from items; with the chat list it is
    # a chat `n` pointing to its last message. The connector performs the real send; the CONFIRM gate (V2-025)
    # already asked for OK before reaching this branch.
    if action == "reply":
        n = payload.get("n")
        text = (payload.get("text") or "").strip()
        if n is not None and text:
            db = load_db()
            target = None
            if db.get("active_chat") is not None:
                target = next((it for it in _renumber(db.get("items", [])) if it.get("n") == n), None)
            else:
                chat = next((c for c in _group_chats(_visible_items(db)) if c.get("n") == n), None)
                if chat:                       # chat -> its last message, for threading/recipient
                    key = (chat["platform"], str(chat["chatId"]))
                    msgs = [it for it in db.get("items", [])
                            if (it.get("platform"), str(it.get("chatId"))) == key]
                    target = msgs[-1] if msgs else None
            if target is not None:
                db.setdefault("pending_reply", []).append({
                    "platform": target.get("platform"),
                    "chatId": target.get("chatId"),
                    "to": target.get("senderId") or target.get("chatId"),
                    "messageId": target.get("messageId"),
                    "subject": target.get("subject", ""),
                    "msgid": target.get("msgid", ""),
                    "text": text,
                })
                # Reply implies READ: also enqueue mark-read for that message and remove it from the list.
                db.setdefault("pending_read", []).append(_key(target))
                db["items"] = [it for it in db.get("items", []) if it is not target]
                store.save(WIDGET_ID, db)
        return view_data()

    # Mute channel: N addresses the same way as read/dismiss depending on context. With an open chat it is a
    # message `n` from `items`; with the chat list it is a chat `n` from `_group_chats`. Same duality already
    # documented in brief.py for read/dismiss/hide.
    if action == "hide":
        n = payload.get("n")
        if n is not None:
            db = load_db()
            platform = chat_id = group = None
            if db.get("active_chat") is not None:
                for it in _renumber(db.get("items", [])):
                    if it.get("n") == n:
                        platform, chat_id = it.get("platform"), it.get("chatId")
                        group = it.get("group") or it.get("from") or ""
                        break
            else:
                match = next((c for c in _group_chats(_visible_items(db)) if c.get("n") == n), None)
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
                store.save(WIDGET_ID, db)
        return view_data()

    # Per-connector NOTIFICATION POLICY (V2-532): how a channel may interrupt — which messages surface
    # proactively (never|direct|important|all) and whether a surfaced batch may be SPOKEN. Voice-settable
    # («no me avises de los grupos de Telegram» is `hide`; «Telegram solo mensajes directos» is this). The
    # decision logic lives in `.policy` (zero-import module) and is the same one notify.surface consults —
    # one rule, two readers, never two copies.
    if action == "set_notify":
        platform = payload.get("platform")
        if platform not in _PLATFORMS:
            return {"ok": False, "error": f"platform must be one of {_PLATFORMS}"}
        from .policy import set_policy
        db = load_db()
        try:
            pol = set_policy(db, platform, notify=payload.get("notify"), speak=payload.get("speak"))
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        store.save(WIDGET_ID, db)
        return {"ok": True, "platform": platform, "policy": pol, **view_data()}

    if action == "unhide":
        platform = payload.get("platform")
        chat_id = payload.get("chatId")
        if platform and chat_id is not None:
            db = load_db()
            key = (platform, str(chat_id))
            db["muted_channels"] = [m for m in db.get("muted_channels", [])
                                     if (m.get("platform"), str(m.get("chatId"))) != key]
            store.save(WIDGET_ID, db)
        return view_data()

    # Open/close a chat thread: pure navigation, addressable by click or voice
    # ([[msg.open:N]]/[[msg.close]], N = the CHAT `n`; see _group_chats). V2-543: also by NAME — the operator
    # says «abre el chat de Jose Vicente», not a number; containment over accent-stripped forms, both ways.
    if action == "open":
        n = payload.get("n")
        name = str(payload.get("name") or payload.get("chat") or "").strip()
        db = load_db()
        chats = _group_chats(_visible_items(db))
        match = None
        if n is not None:
            match = next((c for c in chats if c.get("n") == n), None)
        elif name:
            want = _norm_txt(name)
            if want:
                match = next((c for c in chats
                              if want in _norm_txt(c.get("name")) or _norm_txt(c.get("name")) in want), None)
        if match is None and (n is not None or name):
            return {"ok": False,
                    "error": "no encuentro ese chat — vuelve a llamar a open con el `n` de la lista o con "
                             "`name` tal como aparece en ella",
                    **view_data()}
        if match:
            db["active_chat"] = {"platform": match["platform"], "chatId": match["chatId"]}
            store.save(WIDGET_ID, db)
        return view_data()

    if action == "close":
        db = load_db()
        if db.get("active_chat") is not None:
            db["active_chat"] = None
            store.save(WIDGET_ID, db)
        return view_data()

    # Mark an entire chat read without opening it (voice: [[msg.readchat:N]], N = the CHAT `n`).
    if action == "readchat":
        n = payload.get("n")
        if n is not None:
            db = load_db()
            match = next((c for c in _group_chats(_visible_items(db)) if c.get("n") == n), None)
            if match:
                key = (match["platform"], str(match["chatId"]))
                pending = db.get("pending_read", [])
                keep = []
                for it in db.get("items", []):
                    if (it.get("platform"), str(it.get("chatId"))) == key:
                        pending.append(_key(it))
                    else:
                        keep.append(it)
                db["items"] = keep
                db["pending_read"] = pending
                store.save(WIDGET_ID, db)
        return view_data()

    # ARCHIVE / DELETE in the REAL mailbox (V2-543; email only today). Same `n` addressing as read/dismiss.
    # The item leaves the widget AND the order travels to the platform's connector: archiving here without
    # archiving there would make the widget a lie about the real inbox — the whole point is not having to
    # open the real app afterwards.
    if action in ("archive", "trash"):
        n = payload.get("n")
        mid = payload.get("messageId")
        db = load_db()
        items = _renumber(db.get("items", []))
        hit = next((it for it in items
                    if (n is not None and it.get("n") == n) or (mid and it.get("messageId") == mid)), None)
        if hit is None:
            return {"ok": False,
                    "error": f"no encuentro ese mensaje — vuelve a llamar a {action} con el `n` de la lista",
                    **view_data()}
        if hit.get("platform") != "email":
            return {"ok": False,
                    "error": ("archivar/borrar en la app real solo está soportado para EMAIL hoy — para "
                              "WhatsApp/Telegram usa read (marcar leído) o dismiss (descartar del widget)"),
                    **view_data()}
        db.setdefault(f"pending_{action}", []).append(_key(hit))
        db["items"] = [it for it in db.get("items", []) if it is not hit]
        store.save(WIDGET_ID, db)
        verb = "archivado" if action == "archive" else "enviado a borrar"
        return {"ok": True, "result": {"action": action, "from": hit.get("from"),
                                       "subject": hit.get("subject", ""), "detail": verb},
                **view_data()}

    db = load_db()
    items = _renumber(db.get("items", []))   # align n with what the widget displayed; view_data numbers by order
    pending = db.get("pending_read", [])

    if action in ("read", "dismiss"):
        n = payload.get("n")
        mid = payload.get("messageId")
        keep = []
        for it in items:
            hit = (n is not None and it.get("n") == n) or (mid and it.get("messageId") == mid)
            if hit and action == "read":
                pending.append(_key(it))
            elif not hit:
                keep.append(it)
        db["items"] = keep
    elif action == "clear":
        for it in items:
            pending.append(_key(it))
        db["items"] = []

    db["pending_read"] = pending
    store.save(WIDGET_ID, db)
    return view_data()
