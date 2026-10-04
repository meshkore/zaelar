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
from . import drafts as _drafts
from . import outbound as _outbound
from . import sent as _sent
# The READ side lives in views.py since V2-624 (the architecture ratchet's extraction, along the real seam:
# name resolution, the thread/activity views, peek, the autoresponder previews, and — since V2-626 — the
# open reference and the effective notify policy). One direction only —
# views.py lazy-imports this module where it needs the store or the inbox helpers.
from .views import (_activity_answer, _activity_chats, _autoresponder_preview, _autoresponder_view,
                    _criteria_for, _find_chat_by_name, _group_chats, _notify_policy_view, _open_ref,
                    _chat_digest_answer, _peek_answer, _search_archive_answer, _thread_meta,
                    _thread_view)
from .timing import (  # noqa: E402,F401 — V2-778 F1: moved, imported back under their names
    _COMPOSE_BASE_S, _COMPOSE_LINGER_S, _COMPOSE_MAX_S, _COMPOSE_PER_CHAR_S, _VIEW_TTL_S, _compose_seconds,
    _composing, _email_signature, _fresh_view, _push_view)

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

# Spoken platform names as the operator says them; "" = the unified main list. Structural aliases only — never a
# per-language synonym table beyond what names these three channels.
_PLAT_ALIASES = {
    "whatsapp": "whatsapp", "wasap": "whatsapp", "wa": "whatsapp",
    "telegram": "telegram", "tg": "telegram",
    "email": "email", "correo": "email", "mail": "email", "gmail": "email", "outlook": "email",
    "all": "", "todo": "", "todos": "", "": "", "inbox": "", "principal": "", "general": "", "lista": "",
}


def _empty() -> dict:
    return {
        "platforms": {p: {"status": "off", "qr": None} for p in _PLATFORMS},
        "updated": "",
        "items": [],
        "pending_read": [],
        "pending_reply": [],
        "pending_send": [],    # V2-683: writing to a PERSON, not answering a conversation
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
    # V2-680 — an unsent DRAFT survives too, for the same reason and a stronger one: it is text the operator
    # himself wrote and never sent. A reset clears what arrived; it does not throw away his own writing.
    for k in ("autoresponder", "lens_criteria", "drafts"):
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
    db.setdefault("pending_send", [])
    db.setdefault("pending_history", [])
    db.setdefault("pending_fetch", [])
    db.setdefault("threads", {})
    db.setdefault("updated", "")
    db.setdefault("active_chat", None)
    db.setdefault("draft", None)
    db.setdefault("drafts", {})
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


# What this inbox tells the BRAIN: the always-on summary and the answer to a question
# (`widgets/mensajeria/inbox_read.py`, V2-704). This widget published NEITHER — measured with ten real messages
# in the store, both seams returned zero characters, so «¿me ha escrito alguien?» reached the model with an
# empty block and an empty block answers «no». Re-exported here because `refs.prompt_digest` and
# `nucleo/flash/widget_read` look for them on `data.py`, for every widget, by the same contract.
from .inbox_read import prompt_digest, read_query  # noqa: F401,E402 — re-export


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
    composing = _composing(db)
    writing_here = bool(composing and active_key
                        and (composing.get("platform"), str(composing.get("chatId"))) == active_key)
    if active and not active_items and not writing_here:
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
        # V2-543 — the requested VIEW (platform lens / main list), witness-countered + server-expired.
        "view": _fresh_view(db),
        # V2-546 — where our copy of the open conversation begins, and whether there is any point asking for
        # more. The widget draws a boundary from this instead of letting the thread look like the whole story.
        "thread_meta": thread_meta,
        # V2-611 — the review-first reply: text the operator (by voice or by typing) put in the compose box
        # but has not sent yet. `target` names WHAT it would go to, so a stale draft from a conversation that
        # is no longer open never gets rendered against the wrong screen.
        "draft": db.get("draft") or None,
        # V2-776 L2 — what this card SENT (and what is still leaving), the rows `send_to`'s postcondition reads.
        "sent": _sent.rows(db),
        # V2-680 — one draft PER CONVERSATION, keyed by `_draft_key`. Before this there was exactly one
        # draft in the whole widget, so starting a reply to a second conversation silently destroyed the
        # first. The widget reads its own screen's key out of this map; `draft` above stays the most recent.
        "drafts": dict(db.get("drafts") or {}),
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
        # A message to a person, being written on screen right now (see `_COMPOSE_*`): the card types it into
        # that conversation's box and presses send at `send_at`, the moment the queued order is released.
        "composing": composing,
    }


_BRING_BACK_MAX = 2


def _bring_back_found_mail(payload: dict) -> int:
    """A mail the archive found but this card no longer holds is asked back from the mailbox, attachments included.

    Demo pass 2026-09-28 (full28 E1→E3): «did inworld send me something?» found the receipt in the archive; the card
    holds only the 30 most recent unread, and with newer mail since, the receipt was not among them — «open it» found
    no chat and «send the invoice to quinn» had nothing to forward. The archive keeps the mailbox UID, so the
    card's own «load previous» order (the connector's `fetch_older`, one message just below UID+1) brings exactly
    that mail into its conversation. Never raises; returns how many orders were queued."""
    try:
        from . import views as _v
        db = load_db()
        held = {str(it.get("chatId")) for it in db.get("items", []) if it.get("platform") == "email"}
        held |= {str(k).partition("|")[2] for k in (db.get("threads") or {}) if str(k).startswith("email|")}
        queued, seen = 0, set()
        for r in _v.archive_rows(payload):
            if queued >= _BRING_BACK_MAX:
                break
            chat, uid = str(r.get("chat_id") or ""), str(r.get("msg_id") or "")
            if (r.get("platform") != "email" or r.get("direction") != "in" or not chat or not uid.isdigit()
                    or chat in held or chat in seen):
                continue
            seen.add(chat)
            db.setdefault("pending_history", []).append(
                {"platform": "email", "chatId": chat, "beforeTs": 0, "beforeId": str(int(uid) + 1), "limit": 1})
            queued += 1
        if queued:
            store.save(WIDGET_ID, db)
        return queued
    except Exception:  # noqa: BLE001
        return 0


FOUND_TTL_S = 1800


def _remember_found(payload: dict) -> None:
    """The mail an archive search found, so «open it» has a referent (demo pass 62, E2).

    «did inworld send me something?» found the receipt; its conversation was on the card (a thread with no name,
    brought back by an earlier «load previous»), but not in the inbox list — and «open it» came back as «nothing to
    open», then a repair pass opened the ONE chat the list showed: the wrong mail. What the card last found is a
    fact of the card, like what it last sent. Never raises."""
    try:
        from . import views as _v
        row = next((r for r in _v.archive_rows(payload) if r.get("direction") == "in" and r.get("chat_id")), None)
        if row is None:
            return
        db = load_db()
        body = str(row.get("body") or "")
        subject = body[len("[Asunto: "):body.index("]")] if body.startswith("[Asunto: ") and "]" in body else ""
        db["last_found"] = {"platform": str(row.get("platform") or ""), "chatId": str(row.get("chat_id")),
                            "name": str(row.get("chat_name") or row.get("sender") or row.get("chat_id")),
                            "subject": subject[:120], "at": time.time()}
        store.save(WIDGET_ID, db)
    except Exception:  # noqa: BLE001
        pass


def last_found(db: dict) -> dict | None:
    """The fresh `last_found` of this card, or None."""
    lf = db.get("last_found")
    if isinstance(lf, dict) and lf.get("chatId") and time.time() - float(lf.get("at") or 0) < FOUND_TTL_S:
        return lf
    return None


# V2-778 F1-12 — the action handlers live in `actions.py`, imported back under their names (that module
# reads this one).
from .actions import (  # noqa: E402,F401
    _a_show_view, _a_fetch_now, _a_set_autoresponder, _a_clear_autoresponder,
    _a_search_archive, _a_peek, _a_reply, _a_draft, _a_send_draft, _a_send_to, _a_forward,
    _a_unread, _a_set_signature, _a_set_signature_line, _a_clear_signature, _a_hide, _a_set_notify, _a_unhide,
    _a_open, _a_close, _a_load_more, _a_readchat, _a_archive)


# V2-778 F1-12 — one function per action (in `actions.py`), and `apply_action` is the table lookup. Each body
# is the branch it was, moved verbatim; the contract gate reads the table's keys
# (`widgets/validator._table_actions`).


ACTIONS = {
    "show_view": _a_show_view,
    "fetch_now": _a_fetch_now,
    "set_autoresponder": _a_set_autoresponder,
    "clear_autoresponder": _a_clear_autoresponder,
    "search_archive": _a_search_archive,
    "peek": _a_peek,
    "chat_digest": _a_peek,
    "reply": _a_reply,
    "draft": _a_draft,
    "send_draft": _a_send_draft,
    "send_to": _a_send_to,
    "forward": _a_forward,
    "unread": _a_unread,
    "set_signature": _a_set_signature,
    "set_signature_line": _a_set_signature_line,
    "clear_signature": _a_clear_signature,
    "hide": _a_hide,
    "set_notify": _a_set_notify,
    "unhide": _a_unhide,
    "open": _a_open,
    "close": _a_close,
    "load_more": _a_load_more,
    "readchat": _a_readchat,
    "archive": _a_archive,
    "trash": _a_archive,
}


def apply_action(action: str, payload: dict | None = None) -> dict:
    """Operator actions from the widget, the only widget->backend channel; the widget cannot fetch:
    - read/dismiss/clear mutate the list; marking read enqueues into `pending_read`, drained by the connector.
    - connect/disconnect enqueue a control command into `pending_control` (platform + credentials); the server-side
      supervisor drains it and performs the real connect/disconnect (config/connectors.py + start/stop). This lets
      the user connect Telegram/WhatsApp from the UI without touching .env. data.py remains stdlib-only."""
    payload = payload or {}
    handler = ACTIONS.get(action) if isinstance(action, str) else None
    if handler is not None:
        return handler(action, payload)
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


# V2-778 F1 — the answering actions live in `widgets/mensajeria/answers.py`; `data.answer_action` resolves there on
# first use (a module `__getattr__`: that module reads this one's names, and nothing left here calls it).
def __getattr__(name: str):
    if name == "answer_action":
        from widgets.mensajeria import answers as _answers
        return _answers.answer_action
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
