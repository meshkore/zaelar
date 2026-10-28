#
# Messaging widget data layer. Reads/mutates the unified store (widgets/_data/mensajeria.json), written
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
from . import chatlist as _chatlist
from . import media as _media
from . import drafts as _drafts
from . import held as _held
from . import outbound as _outbound
from . import sent as _sent
from . import names as _names   # V2-819: one resolver names every conversation the card shows
# The READ side lives in views.py (names, thread/activity views, peek, autoresponder previews, the open reference,
# the effective notify policy). One direction only: views.py lazy-imports this module where it needs the store.
from .views import (_activity_answer, _activity_chats, _autoresponder_preview, _autoresponder_view,
                    _criteria_for, _find_chat_by_name, _group_chats, _notify_policy_view, _open_ref,
                    _chat_digest_answer, _peek_answer, _search_archive_answer, _thread_meta,
                    _thread_view)
from .timing import (  # noqa: E402,F401 — V2-778 F1: moved, imported back under their names
    _COMPOSE_BASE_S, _COMPOSE_LINGER_S, _COMPOSE_MAX_S, _COMPOSE_PER_CHAR_S, _VIEW_TTL_S, _compose_seconds,
    _composing, _email_signature, _fresh_view, _push_view)

# The store shape (id, platforms, empty/reset state, load, the numbered list) lives in shape.py.
from .shape import (  # noqa: F401 — re-exported under their names
    WIDGET_ID, _PLATFORMS, _empty, blank, load_db, _renumber, _key, _visible_items)

# Which platforms can go BACK and fetch older messages (V2-546) — a statement about each transport: MTProto and IMAP
# serve history from the server; WhatsApp asks its phone and may honestly come back empty. Outside it: no button.
_HISTORY_PLATFORMS = ("telegram", "email", "whatsapp")
_HISTORY_LIMIT = 30
_OPENING_S = 45                     # a chat opened from the list waits this long for its messages
# Which platforms can serve a PLATFORM-WIDE pull (V2-624), a transport statement: Telegram enumerates its dialogs,
# IMAP searches by date; WhatsApp's bridge has no «list recent chats» door, so it is refused with the reason.
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


# What this inbox tells the BRAIN: the always-on summary and the answer to a question (`inbox_read.py`, V2-704).
# Re-exported because `refs.prompt_digest` and `nucleo/flash/widget_read` look for them on `data.py`.
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
    # An open chat shows the CONVERSATION (what was said, ours included), not only what is still unread (V2-546).
    active_items = _thread_view(db, active, pending_here) if active_key else []
    thread_meta = _thread_meta(db, active) if active_key else None
    composing = _composing(db)
    writing_here = bool(composing and active_key
                        and (composing.get("platform"), str(composing.get("chatId"))) == active_key)
    opening = db.get("opening") or {}
    still_opening = bool(active_key and opening.get("key") == f"{active_key[0]}|{active_key[1]}"
                         and time.time() - float(opening.get("at") or 0) < _OPENING_S)
    if active and not active_items and not writing_here and not still_opening:
        # Auto-close only when there is nothing at all — no pending item AND no history: he can still read the rest.
        db["active_chat"] = None
        store.save(WIDGET_ID, db)
        active = None
        thread_meta = None

    return _names.apply({
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
        # How each channel may interrupt (V2-532), normalized through the policy module: the reader always sees
        # the effective values, whatever partial or legacy shape the store holds.
        "notify_policy": _notify_policy_view(db),
        # V2-543 — the requested VIEW (platform lens / main list), witness-countered + server-expired.
        "view": _fresh_view(db),
        # Where our copy of the open conversation begins and whether more can be asked (V2-546): the boundary the
        # widget draws so the thread does not look like the whole story.
        "thread_meta": thread_meta,
        # The review-first reply (V2-611): text in the compose box not sent yet; `target` names what it would go
        # to, so a stale draft is never rendered against the wrong screen.
        "draft": db.get("draft") or None,
        # V2-776 L2 — what this card SENT (and what is still leaving), the rows `send_to`'s postcondition reads.
        "sent": _sent.rows(db),
        # V2-819 — the card's own sends and their outcome: it clears the box on «sent» and keeps his text otherwise.
        "outbox": _sent.outbox_view(db),
        # One draft PER CONVERSATION, keyed by `_draft_key` (V2-680): a second reply never destroys the first. The
        # widget reads its own screen's key; `draft` above stays the most recent.
        "drafts": dict(db.get("drafts") or {}),
        # His OWN signature (V2-611), read fresh so a settings edit shows at once. [] = none; nothing is appended.
        "email_signature": _email_signature(),
        # His per-platform lens criteria and, per platform that has one, the matching conversations (V2-624).
        # Both empty unless he set something.
        "lens_criteria": {p: c for p in _PLATFORMS if (c := _criteria_for(db, p))},
        "activity_chats": [row for p in _PLATFORMS if (c := _criteria_for(db, p))
                           for row in _activity_chats(db, p, c["window_h"])],
        # The autoresponder state, for the settings panel and read_widget (V2-624); only configured platforms.
        "autoresponder": _autoresponder_view(db),
        # A message to a person, being written on screen right now (see `_COMPOSE_*`): the card types it into
        # that conversation's box and presses send at `send_at`, the moment the queued order is released.
        "composing": composing,
        # The chat list of each list platform (chatlist.py): what the account's real app would show first.
        "chat_list": {p: _chatlist.view(db, p) for p in _chatlist.LIST_PLATFORMS
                      if (db.get("platforms") or {}).get(p, {}).get("status") == "connected"
                      or (db.get("chat_index") or {}).get(p)},
        "opening": still_opening,
        "media_days": _media.days(db),
        # The email section as a mail client (mailbox.py): folders, the current folder's rows, what is open.
        "mailbox": _mailbox.view(db),
    })


# What an archive search found (brought back, remembered for «open it») lives in found_mail.py.
from .found_mail import (  # noqa: E402,F401 — re-exported under their names
    _BRING_BACK_MAX, _bring_back_found_mail, FOUND_TTL_S, _remember_found, last_found)


# The action handlers live in `actions/`, imported back under their names (that package reads this module).
from .actions import (  # noqa: E402,F401
    _a_show_view, _a_fetch_now, _a_set_autoresponder, _a_clear_autoresponder,
    _a_search_archive, _a_peek, _a_reply, _a_draft, _a_send_draft, _a_send_to, _a_forward,
    _a_unread, _a_set_signature, _a_set_signature_line, _a_clear_signature, _a_hide, _a_set_notify, _a_unhide,
    _a_open, _a_close, _a_load_more, _a_readchat, _a_archive, _a_chats_more,
    _a_set_media_days, _a_create_group, _a_cancel_send)
from .mail_actions import (  # noqa: E402,F401
    _a_mail_folder, _a_mail_more, _a_mail_open, _a_mail_back, _a_open_draft, _a_save_draft, _a_discard_draft,
    _a_compose, _a_mail_sort)
from . import mailbox as _mailbox  # noqa: E402


# One function per action and `apply_action` is the table lookup (V2-778); the contract gate reads the table's
# keys (`widgets/validator._table_actions`).


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
    "cancel_send": _a_cancel_send,
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
    "chats_more": _a_chats_more,
    "set_media_days": _a_set_media_days,
    "create_group": _a_create_group,
    "readchat": _a_readchat,
    "archive": _a_archive,
    "trash": _a_archive,
    "mail_folder": _a_mail_folder,
    "mail_more": _a_mail_more,
    "mail_open": _a_mail_open,
    "mail_back": _a_mail_back,
    "open_draft": _a_open_draft,
    "save_draft": _a_save_draft,
    "discard_draft": _a_discard_draft,
    "compose": _a_compose,
    "mail_sort": _a_mail_sort,
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


# `data.answer_action` resolves lazily (a module `__getattr__`) to the card's answering door (V2-778): that module
# reads this one's names, and nothing here calls it.
def __getattr__(name: str):
    if name == "answer_action":
        from widgets.mensajeria import card_send as _card   # V2-819: the card's Send is vetoed first, then answers
        return _card.answer_action
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ── V2-800 · the consent rule's hooks and the pending-work rows live in consent_hooks.py, re-exported here: ──
# `nucleo/flash/frontend.py`, `nucleo/pending_work.py` and `widgets/text_home.py` look for them on `data.py`.
from .consent_hooks import (  # noqa: E402,F401
    held_row, consent_scope, pending_rows, claim_text, recent_facts)
