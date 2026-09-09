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

from .. import store
# The READ side lives in views.py since V2-624 (the architecture ratchet's extraction, along the real seam:
# name resolution, the thread/activity views, peek, the autoresponder previews, and — since V2-626 — the
# open reference and the effective notify policy). One direction only —
# views.py lazy-imports this module where it needs the store or the inbox helpers.
from .views import (_activity_answer, _activity_chats, _autoresponder_preview, _autoresponder_view,
                    _criteria_for, _find_chat_by_name, _group_chats, _notify_policy_view, _open_ref,
                    _peek_answer, _thread_meta, _thread_view)

WIDGET_ID = "mensajeria"
_PLATFORMS = ("whatsapp", "telegram", "email")   # email: V2-051
# Which platforms can actually go BACK and fetch older messages (V2-546). This is a statement about each
# transport, not a preference: Telegram's MTProto serves arbitrary history from the account itself; IMAP holds
# the whole mailbox on the server; WhatsApp keeps history on the DEVICE and a linked client can only ask its
# phone for it, so it is offered and may honestly come back empty. A platform outside this list gets no button
# at all — offering one that cannot work is worse than not offering it.
_HISTORY_PLATFORMS = ("telegram", "email", "whatsapp")
_HISTORY_LIMIT = 30
# V2-624 — which platforms can serve a PLATFORM-WIDE pull («tráete las conversaciones con actividad en las
# últimas 72 h»). A transport statement, like _HISTORY_PLATFORMS above: Telegram enumerates its own dialogs,
# IMAP searches the whole mailbox by date; WhatsApp's bridge can only relay what the phone pushes plus
# per-chat history — there is no «list recent chats» door to ask through, and offering one that cannot work
# is worse than saying so.
_FETCH_PLATFORMS = ("telegram", "email")
_FETCH_DEFAULT_H = 72.0
_WINDOW_MAX_H = 24.0 * 90            # criteria and fetches are bounded: 90 days is «the past», not a lens
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
        "pending_history": [],
        "threads": {},         # V2-546: the CONVERSATIONS (see thread.py). The inbox above is what still wants
                               # attention; this is what was said, and reading no longer destroys it.
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
    # V2-624 — the operator's own CONFIGURATION survives a reset the way the connection state does: an
    # autoresponder set for his vacation and his per-platform view criteria are not «messages and queues»,
    # and a reset that silently stops answering people in his name is a worse surprise than any stale list.
    for k in ("autoresponder", "lens_criteria"):
        if isinstance(cur.get(k), dict) and cur.get(k):
            fresh[k] = cur[k]
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
    db.setdefault("pending_history", [])
    db.setdefault("pending_fetch", [])
    db.setdefault("threads", {})
    db.setdefault("updated", "")
    db.setdefault("active_chat", None)
    db.setdefault("draft", None)
    db.setdefault("lens_criteria", {})
    return db


def _renumber(items: list) -> list:
    for i, it in enumerate(items, 1):
        it["n"] = i
    return items


def _key(it: dict) -> dict:
    return {"platform": it.get("platform"), "chatId": it.get("chatId"),
            "messageId": it.get("messageId"), "senderId": it.get("senderId")}


def _visible_items(db: dict) -> list:
    """Non-muted, renumbered items: the same base list seen by the widget and the brain.

    V2-607 — each item also carries `highlight`: does it meet the criterion for the SUMMARY tab (default: it is
    addressed to him). Nothing is filtered out here. The per-platform lenses show every unread message, and the
    unified list uses this flag to put only what he asked for in front of him. Computed at read time, not stored,
    so changing the policy re-sorts the screen he is already looking at instead of only the mail that arrives next.
    """
    from . import policy as _policy
    muted_channels = db.get("muted_channels", [])
    muted_keys = {(m.get("platform"), str(m.get("chatId"))) for m in muted_channels}
    pols: dict = {}
    out = []
    for it in db.get("items", []):
        if (it.get("platform"), str(it.get("chatId"))) in muted_keys:
            continue
        plat = it.get("platform") or "?"
        pol = pols.get(plat)
        if pol is None:
            pol = pols[plat] = _policy.policy_for(db, plat)
        it = dict(it)
        it["highlight"] = _policy.wants_highlight(pol, it)
        out.append(it)
    return _renumber(out)


def _resolve_target(db: dict, n=None, mid: str | None = None) -> dict | None:
    """The identity `draft`/`send_draft` reply to (V2-611) — NOT `reply`, which keeps its own original,
    separately-tested resolution (chat-list numbering when no thread is open) unchanged.

    `n`/`messageId` resolve against the flat renumbered list — the same space read/dismiss/archive/trash/hide
    already use, and the same meaning `n` has there (an ITEM, never a `_group_chats` row). The compose bar
    always has the concrete item in hand for a single email (both `n` and `messageId`), so this never needs
    to guess between the two numbering spaces the way `reply`'s legacy fallback does. With NEITHER given and
    a thread open, it resolves to the conversation itself: the operator answering «the person I'm talking
    to», not a specific past message."""
    if n is not None or mid:
        # `n` only exists on an item once `_renumber` assigns it — a raw stored item never carries one, so
        # this must renumber first, exactly like every other n-addressed action in this file (read/dismiss/
        # archive/trash/hide). Skipping it would make a bare `n` never resolve to anything at all outside a
        # test fixture that happened to pre-set the field (the mistake this comment exists to prevent again).
        items = _renumber(db.get("items", []))
        return next((it for it in items
                     if (n is not None and it.get("n") == n) or (mid and it.get("messageId") == mid)), None)
    active = db.get("active_chat")
    if active is None:
        return None
    key = (active.get("platform"), str(active.get("chatId")))
    msgs = [it for it in db.get("items", []) if (it.get("platform"), str(it.get("chatId"))) == key]
    if msgs:
        return msgs[-1]
    # Every pending item in this thread is already read/answered — nothing left in `items` to mark-read or
    # remove, but the conversation still has an identity to reply to (V2-546: answering must not require an
    # unread message to exist first). `_enqueue_reply` reads only platform/chatId/senderId from this shape.
    return {"platform": key[0], "chatId": key[1]}


def _enqueue_reply(db: dict, target: dict, text: str) -> None:
    """The one place a reply/draft actually gets queued for the connector to send for real. A real item
    ALWAYS carries `messageId` (set on ingestion, by every connector) — including one resolved via `reply`'s
    own chat-grouping fallback, which never goes through `_renumber` and so never has `n` set either, which
    is why `n` cannot be the "is this real" signal here. Only the true synthetic thread-identity target (see
    `_resolve_target`, `{"platform", "chatId"}` alone) has neither, and nothing pending to remove — correct,
    since there was no pending item to begin with."""
    db.setdefault("pending_reply", []).append({
        "platform": target.get("platform"), "chatId": target.get("chatId"),
        "to": target.get("senderId") or target.get("chatId"),
        "messageId": target.get("messageId"), "subject": target.get("subject", ""),
        "msgid": target.get("msgid", ""), "text": text,
    })
    if target.get("messageId") is not None:
        db.setdefault("pending_read", []).append(_key(target))
        db["items"] = [it for it in db.get("items", []) if it is not target]


def view_data(q: str = "") -> dict:
    db = load_db()
    items = _visible_items(db)
    chats = _group_chats(items)
    muted_channels = db.get("muted_channels", [])

    active = db.get("active_chat")
    active_key = (active.get("platform"), str(active.get("chatId"))) if active else None
    pending_here = [it for it in items if (it.get("platform"), str(it.get("chatId"))) == active_key] \
        if active_key else []
    # V2-546 — an open chat shows the CONVERSATION (what was said, ours included), not only what is still
    # unread. Before this the two were the same list, so answering every message emptied the thread and the
    # widget auto-closed it: there was nothing to come back to and no way to continue a conversation.
    active_items = _thread_view(db, active, pending_here) if active_key else []
    thread_meta = _thread_meta(db, active) if active_key else None
    if active and not active_items:
        # Only when there is nothing at all — no pending item AND no history. The auto-close existed because
        # reading used to destroy the messages; keeping it unconditional would now throw the operator out of a
        # conversation he can still read.
        db["active_chat"] = None
        store.save(WIDGET_ID, db)
        active = None
        thread_meta = None

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
        # V2-546 — where our copy of the open conversation begins, and whether there is any point asking for
        # more. The widget draws a boundary from this instead of letting the thread look like the whole story.
        "thread_meta": thread_meta,
        # V2-611 — the review-first reply: text the operator (by voice or by typing) put in the compose box
        # but has not sent yet. `target` names WHAT it would go to, so a stale draft from a conversation that
        # is no longer open never gets rendered against the wrong screen.
        "draft": db.get("draft") or None,
        # V2-611 — the operator's OWN signature, read fresh (a local config file, not a secret) so an edit in
        # the settings screen is visible immediately. [] = none set; the connector appends nothing at all.
        "email_signature": _email_signature(),
        # V2-624 — the operator's per-platform lens criteria («actividad en las últimas 72 h») and, for each
        # platform that HAS one, the conversations matching it. Both empty unless he set something: the classic
        # lens costs nothing new.
        "lens_criteria": {p: c for p in _PLATFORMS if (c := _criteria_for(db, p))},
        "activity_chats": [row for p in _PLATFORMS if (c := _criteria_for(db, p))
                           for row in _activity_chats(db, p, c["window_h"])],
        # V2-624 — the autoresponder state, for the settings panel and read_widget. Only platforms with any
        # config at all; {} costs nothing.
        "autoresponder": _autoresponder_view(db),
    }


def _email_signature() -> list:
    try:
        from connectors.email import config as _email_cfg
        return _email_cfg.signature_lines()
    except Exception:
        return []


def answer_action(action: str, payload: dict | None = None) -> dict | None:
    """READ-ONLY answer/validation for the backed route (V2-543). The owner's mailbox keeps one writer but
    swallowed every return: `show_view`'s answer (the matching chats) and the teach-the-shape errors never
    reached the brain — the screen moved by SSE while the turn got a bare `{"queued": true}`. This computes
    the ANSWER and vetoes an invalid order without touching the store; the mutation still goes through the
    owner. Must never call store.save."""
    payload = payload or {}
    if action == "show_view":
        raw = str(payload.get("platform") or payload.get("view") or "").strip().lower()
        if raw not in _PLAT_ALIASES:
            return {"ok": False,
                    "error": "no reconozco esa vista — vuelve a llamar a show_view con `platform`: 'all' "
                             "(la lista principal unificada), 'whatsapp', 'telegram' o 'email'"}
        platform = _PLAT_ALIASES[raw]
        db = load_db()
        chats = [c for c in _group_chats(_visible_items(db))
                 if not platform or c.get("platform") == platform]
        result = {"platform": platform or "all", "count": len(chats),
                  "chats": [{"n": c.get("n"), "name": c.get("name"), "platform": c.get("platform"),
                             "count": c.get("count")} for c in chats[:12]]}
        # V2-624 — PREVIEW of the criterion the owner is about to persist (this hook must never write): with
        # `window_h` in the order, answer with the activity rows that window yields RIGHT NOW; without it,
        # with whatever criterion is already set.
        if platform and "window_h" in payload:
            try:
                win = float(payload.get("window_h") or 0)
            except (TypeError, ValueError):
                return {"ok": False,
                        "error": "window_h tiene que ser un número de HORAS (72 = últimos 3 días); "
                                 "0 quita el criterio y vuelve a la vista de pendientes"}
            if win > 0:
                rows = _activity_chats(db, platform, min(win, _WINDOW_MAX_H))
                result.update({"criteria": {"window_h": min(win, _WINDOW_MAX_H)},
                               "activity_count": len(rows),
                               "activity": [{"name": r["name"], "isGroup": r["isGroup"],
                                             "unread": r["unread"], "inWindow": r["inWindow"]}
                                            for r in rows[:12]]})
                if platform in _FETCH_PLATFORMS and len(rows) < 3:
                    result["detail"] = (f"solo tengo {len(rows)} conversación(es) guardadas en esa ventana — "
                                        f"fetch_now {{platform:'{platform}'}} trae del conector la actividad "
                                        f"real del período")
        else:
            result.update(_activity_answer(db, platform))
        return {"result": result}
    if action == "fetch_now":
        raw = str(payload.get("platform") or "").strip().lower()
        platform = _PLAT_ALIASES.get(raw, raw)
        if platform not in _FETCH_PLATFORMS:
            if platform == "whatsapp":
                return {"ok": False,
                        "error": ("WhatsApp no permite pedirle al teléfono las conversaciones en bloque: lo "
                                  "nuevo llega solo en tiempo real, y de un chat CONCRETO que ya tengamos sí "
                                  "puedo traer mensajes anteriores (open + load_more)")}
            return {"ok": False,
                    "error": "fetch_now necesita `platform`: 'telegram' o 'email'"}
        try:
            since = float(payload.get("since_hours") or _FETCH_DEFAULT_H)
        except (TypeError, ValueError):
            since = _FETCH_DEFAULT_H
        since = max(1.0, min(since, _WINDOW_MAX_H))
        return {"result": {"asked": True, "platform": platform, "since_hours": since,
                           "detail": "pedido al conector — las conversaciones de ese período irán apareciendo "
                                     "en unos segundos; vuelve a mirar (show_view o peek) cuando lleguen"}}
    if action == "peek":
        return _peek_answer(payload)
    if action == "set_autoresponder":
        return _autoresponder_preview(payload)
    if action == "clear_autoresponder":
        return {"result": {"cleared": True,
                           "detail": "autorespondedor apagado y borrado — confírmaselo al operador"}}
    if action == "open":
        n, name = _open_ref(payload)
        if n is None and not name:
            return None
        db = load_db()
        hit = next((c for c in _group_chats(_visible_items(db)) if c.get("n") == n), None) \
            if n is not None else _find_chat_by_name(db, name)
        if hit is None:
            return {"ok": False,
                    "error": "no encuentro ese chat — vuelve a llamar a open con el `n` de la lista o con "
                             "`name` tal como aparece en ella"}
        return {"result": {"opened": hit.get("name"), "platform": hit.get("platform")}}
    if action == "load_more":
        db = load_db()
        chat = db.get("active_chat")
        if payload.get("platform") and payload.get("chatId") is not None:
            chat = {"platform": payload.get("platform"), "chatId": payload.get("chatId")}
        if not chat:
            return {"ok": False,
                    "error": "no hay ninguna conversación abierta — abre primero el chat con open y vuelve a "
                             "llamar a load_more"}
        if chat.get("platform") not in _HISTORY_PLATFORMS:
            return {"ok": False,
                    "error": f"traer mensajes anteriores no está soportado para {chat.get('platform')} todavía"}
        if (_thread_meta(db, chat) or {}).get("complete"):
            return {"result": {"loaded": 0, "complete": True,
                               "detail": "ya tienes el principio de esta conversación"}}
        return {"result": {"asked": True, "platform": chat.get("platform"),
                           "detail": "se los he pedido a la app; aparecerán arriba en cuanto lleguen"}}
    if action in ("archive", "trash"):
        n = payload.get("n")
        mid = payload.get("messageId")
        items = _visible_items(load_db())
        hit = next((it for it in items
                    if (n is not None and it.get("n") == n) or (mid and it.get("messageId") == mid)), None)
        if hit is None:
            return {"ok": False,
                    "error": f"no encuentro ese mensaje — vuelve a llamar a {action} con el `n` de la lista"}
        if hit.get("platform") != "email":
            return {"ok": False,
                    "error": ("archivar/borrar en la app real solo está soportado para EMAIL hoy — para "
                              "WhatsApp/Telegram usa read (marcar leído) o dismiss (descartar del widget)")}
        return {"result": {"action": action, "from": hit.get("from"), "subject": hit.get("subject", "")}}
    return None


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
                crit[platform] = {"window_h": min(win, _WINDOW_MAX_H)}
            else:
                crit.pop(platform, None)
        _push_view(db, platform)
        store.save(WIDGET_ID, db)
        out = view_data()
        chats = [c for c in out.get("chats", []) if not platform or c.get("platform") == platform]
        result = {"platform": platform or "all", "count": len(chats),
                  "chats": [{"n": c.get("n"), "name": c.get("name"), "platform": c.get("platform"),
                             "count": c.get("count")} for c in chats[:12]]}
        result.update(_activity_answer(load_db(), platform))
        return {"ok": True, "result": result, **out}

    # PULL through the connector, on demand (V2-624 — the operator's «¿puedes ir al conector y chupar más
    # mensajes?», refused honestly on 2026-09-08 because no such door existed). Enqueues a platform-wide
    # fetch the connector serves against its real source; what arrives lands in the CONVERSATIONS as
    # scrollback (never in triage — pulling the past must not interrupt anybody).
    if action == "fetch_now":
        raw = str(payload.get("platform") or "").strip().lower()
        platform = _PLAT_ALIASES.get(raw, raw)
        if platform not in _FETCH_PLATFORMS:
            if platform == "whatsapp":
                return {"ok": False,
                        "error": ("WhatsApp no permite pedirle al teléfono las conversaciones en bloque: lo "
                                  "nuevo llega solo en tiempo real, y de un chat CONCRETO que ya tengamos sí "
                                  "puedo traer mensajes anteriores (open + load_more)")}
            return {"ok": False,
                    "error": "fetch_now necesita `platform`: 'telegram' o 'email' (WhatsApp no soporta la "
                             "traída en bloque; ver su propio error)"}
        try:
            since = float(payload.get("since_hours") or _FETCH_DEFAULT_H)
        except (TypeError, ValueError):
            since = _FETCH_DEFAULT_H
        since = max(1.0, min(since, _WINDOW_MAX_H))
        db = load_db()
        db.setdefault("pending_fetch", []).append({"platform": platform, "since_hours": since})
        store.save(WIDGET_ID, db)
        return {"ok": True,
                "result": {"asked": True, "platform": platform, "since_hours": since,
                           "detail": "se lo he pedido al conector; las conversaciones de ese período irán "
                                     "apareciendo en unos segundos"},
                **view_data()}

    # THE AUTORESPONDER (V2-624 — the INI-014 «Phase 4» go-ahead). Config only: the decision runs in
    # autorespond.py at the owner's ingest, the send travels the same reply seam a dictated reply uses.
    if action == "set_autoresponder":
        from . import autorespond
        raw = str(payload.get("platform") or "all").strip().lower()
        plats = list(_PLATFORMS) if raw in ("all", "todas", "todos", "") else [_PLAT_ALIASES.get(raw, raw)]
        if any(p not in _PLATFORMS for p in plats):
            return {"ok": False,
                    "error": "set_autoresponder necesita `platform`: 'whatsapp', 'telegram', 'email' o 'all'"}
        text = payload.get("text")
        enabled = payload.get("enabled")
        db = load_db()
        if enabled and not str(text or "").strip() and \
                not any(autorespond.config_for(db, p)["text"] for p in plats):
            return {"ok": False,
                    "error": "no hay ningún mensaje que responder — pásame `text` con lo que debe contestar"}
        try:
            for p in plats:
                autorespond.set_config(db, p, text=text, hours=payload.get("hours"), enabled=enabled)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        store.save(WIDGET_ID, db)
        return {"ok": True, "result": {"autoresponder": _autoresponder_view(db)}, **view_data()}

    if action == "clear_autoresponder":
        from . import autorespond
        raw = str(payload.get("platform") or "all").strip().lower()
        plats = list(_PLATFORMS) if raw in ("all", "todas", "todos", "") else [_PLAT_ALIASES.get(raw, raw)]
        db = load_db()
        for p in plats:
            if p in _PLATFORMS:
                autorespond.clear_config(db, p)
        store.save(WIDGET_ID, db)
        return {"ok": True, "result": {"autoresponder": _autoresponder_view(db)}, **view_data()}

    # `peek` is ANSWER-ONLY (V2-624): answer_action returns the conversation's content and nothing here has
    # anything to mutate. Falling through to the generic branch would re-save the store for a read.
    if action == "peek":
        return view_data()

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
        # UNCHANGED contract (V2-521, tested): `n` means an item in the open thread, or a CHAT in the chat
        # list otherwise — the same duality `hide` documents. `draft`/`send_draft` below are the new,
        # unambiguous path (`n`/`messageId` address one ITEM directly, matching archive/trash's own meaning
        # of `n` for the flat email list); `reply` keeps its original resolution so nothing that already
        # depends on it — voice included — changes behavior.
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
                _enqueue_reply(db, target, text)
                store.save(WIDGET_ID, db)
        return view_data()

    # V2-611 — DRAFT then SEND, as a pair: dictating a reply (or typing it) fills a visible box the operator
    # can read before anything goes out; `send_draft` is the separate, deliberate act that actually sends —
    # by the widget's own button or by a later voice order («envíalo»). `reply` above still exists for a
    # one-shot model-dictated reply (CONFIRM-gated, unchanged) — this is the review-first path instead.
    if action == "draft":
        text = str(payload.get("text") or "")
        db = load_db()
        target = _resolve_target(db, payload.get("n"), payload.get("messageId"))
        if target is None:
            return {"ok": False, "error": "no_target",
                     "message": "No sé a qué conversación o mensaje se refiere el borrador."}
        if not text.strip():
            db["draft"] = None
            store.save(WIDGET_ID, db)
            return {"ok": True, "cleared": True}
        db["draft"] = {"text": text[:4000],
                        "target": {k: target.get(k) for k in
                                   ("platform", "chatId", "senderId", "messageId", "subject", "msgid", "n")},
                        "at": int(time.time())}
        store.save(WIDGET_ID, db)
        return {"ok": True, "text": db["draft"]["text"]}

    if action == "send_draft":
        db = load_db()
        draft = db.get("draft") or {}
        text = str(draft.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "no_draft", "message": "No hay ningún borrador que enviar."}
        stored = draft.get("target") or {}
        # Re-resolve against the LIVE item, so a target that changed since the draft was written (answered
        # elsewhere, read from the real app) is not blindly replied to under a stale identity — same
        # resolution `reply` itself uses. Falls back to the stored identity when nothing live matches: the
        # conversation's own platform/chatId are still enough to send to, even with no pending item left.
        target = _resolve_target(db, stored.get("n"), stored.get("messageId")) or stored
        _enqueue_reply(db, target, text)
        db["draft"] = None
        store.save(WIDGET_ID, db)
        return {"ok": True, "to": target.get("senderId") or target.get("chatId"), "text": text}

    # V2-611 — the EMAIL SIGNATURE, appended once by the connector at real send time (service.py's
    # `_drain_replies`), never here: this only writes the config the connector reads. `config/connectors.py`
    # is the SAME store the connect wizard already writes to for email — signature_lines is one more field
    # on the same "email" entry, not a new mechanism.
    if action == "set_signature":
        lines = payload.get("lines")
        if not isinstance(lines, list):
            return {"ok": False, "error": "bad_lines", "message": "Dame las líneas de la firma."}
        lines = [str(x).strip()[:200] for x in lines[:10]]
        while lines and not lines[-1]:
            lines.pop()
        from config import connectors as _conn_store
        _conn_store.set("email", {"signature_lines": lines})
        return {"ok": True, "lines": lines}

    if action == "set_signature_line":
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

    if action == "clear_signature":
        from config import connectors as _conn_store
        _conn_store.set("email", {"signature_lines": []})
        return {"ok": True, "lines": []}

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
            pol = set_policy(db, platform, notify=payload.get("notify"), speak=payload.get("speak"),
                             highlight=payload.get("highlight"))
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
        n, name = _open_ref(payload)
        db = load_db()
        # V2-624 — a DIRECT identity (platform + chatId), the address an activity-view row carries. Only a
        # conversation we actually hold: opening an arbitrary identity would paint an empty thread.
        if payload.get("platform") and payload.get("chatId") is not None and n is None and not name:
            from . import thread as _th
            key_ = (payload.get("platform"), payload.get("chatId"))
            if _th.window(db, *key_) or any(
                    (it.get("platform"), str(it.get("chatId"))) == (key_[0], str(key_[1]))
                    for it in db.get("items", [])):
                db["active_chat"] = {"platform": key_[0], "chatId": key_[1]}
                store.save(WIDGET_ID, db)
                return view_data()
            return {"ok": False, "error": "no tengo esa conversación guardada", **view_data()}
        chats = _group_chats(_visible_items(db))
        match = None
        if n is not None:
            # `n` addresses the LIST on screen and nothing else — a number has no meaning for a conversation
            # that is not in it, and guessing one would open the wrong chat.
            match = next((c for c in chats if c.get("n") == n), None)
        elif name:
            match = _find_chat_by_name(db, name)
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

    # LOAD PREVIOUS messages of the open conversation (V2-546) — by button or by voice («tráeme los anteriores»).
    # Enqueues an order the platform's connector fulfils against its real source; nothing is fabricated here.
    if action == "load_more":
        db = load_db()
        chat = db.get("active_chat")
        if payload.get("platform") and payload.get("chatId") is not None:
            chat = {"platform": payload.get("platform"), "chatId": payload.get("chatId")}
        if not chat:
            return {"ok": False,
                    "error": "no hay ninguna conversación abierta — abre primero el chat con open y vuelve a "
                             "llamar a load_more",
                    **view_data()}
        platform = chat.get("platform")
        if platform not in _HISTORY_PLATFORMS:
            return {"ok": False,
                    "error": f"traer mensajes anteriores no está soportado para {platform} todavía",
                    **view_data()}
        info = _thread_meta(db, chat) or {}
        if info.get("complete"):
            return {"ok": True, "result": {"loaded": 0, "complete": True,
                                           "detail": "ya tienes el principio de esta conversación"},
                    **view_data()}
        try:
            limit = max(1, min(100, int(payload.get("limit") or _HISTORY_LIMIT)))
        except (TypeError, ValueError):
            limit = _HISTORY_LIMIT
        db.setdefault("pending_history", []).append({
            "platform": platform, "chatId": chat.get("chatId"),
            "beforeTs": info.get("oldest_ts") or 0, "beforeId": info.get("oldest_id") or "",
            "limit": limit,
        })
        store.save(WIDGET_ID, db)
        return {"ok": True,
                "result": {"asked": limit, "platform": platform,
                           "detail": "se los he pedido a la app; aparecerán arriba en cuanto lleguen"},
                **view_data()}

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
