#
# store — the UNIFIED messaging store. ONE file (widgets/_data/mensajeria.json) where ALL connectors
# (WhatsApp, Telegram, ...) write, and which the single widget READS. Reuses the atomic primitive from
# widgets/store.py (tmp+rename write -> readers never see a half-written file).
#
# Shape:
#   { platforms: { whatsapp:{status,qr}, telegram:{status,qr} },
#     updated,
#     items:[{n, platform, from, group, isGroup, body, urgencia, dirigido_a_mi, motivo, messageId, chatId, senderId}],
#     pending_read:[{platform, chatId, messageId, senderId}] }
#
# CONCURRENCY: single process, all connectors in the same loop. Each helper is a SYNCHRONOUS read-modify-write with
# no await in the middle -> no interleaving inside one operation. `n` is NOT persisted as identity: view_data/_renumber
# assigns it by urgency order, so the number the operator sees == the number the brain uses.
#
# This package is the FACADE: everything product code and tests reach is a name on this module (they patch
# `store.load`, `store._to_memory`, …), so the siblings read their collaborators back through it.
#   media.py   — files that travel with a message      taken.py  — the durable ledger of what came in
#   fanout.py  — directory / archive / memory copies   sync.py   — what the connector reports back
#   queues.py  — the orders the widget leaves and a connector drains
#
import time

WIDGET_ID = "mensajeria"
PLATFORMS = ("whatsapp", "telegram", "email")  # email: V2-051 (IMAP/SMTP, same unified shape)
_RANK = {"alta": 0, "media": 1, "baja": 2}


def _now() -> str:
    return time.strftime("%H:%M:%S")


def _empty() -> dict:
    return {
        "platforms": {p: {"status": "off", "qr": None} for p in PLATFORMS},
        "updated": "",
        "items": [],
        "pending_read": [],
        "pending_reply": [],
        "pending_send": [],        # V2-683: writing to a PERSON, not answering a conversation
        "pending_control": [],
        "pending_history": [],
        "muted_channels": [],
        "notify_policy": {},
        "threads": {},
        "taken": [],
    }


def _wstore():
    # lazy: do not couple messaging import-time to the widgets domain (2026-07-17 modularity audit)
    from widgets import store
    return store


def _thread():
    # lazy, same reason as _wstore. The CONVERSATION rules (cap, order, dedup, read watermark) live in the widget
    # package because `data.py` may not import `connectors` — one copy, read from both sides (V2-546).
    from widgets.mensajeria import thread
    return thread


def load() -> dict:
    db = _wstore().load(WIDGET_ID, _empty())
    if not isinstance(db.get("platforms"), dict):
        db["platforms"] = {}
    for p in PLATFORMS:
        if not isinstance(db["platforms"].get(p), dict):
            db["platforms"][p] = {"status": "off", "qr": None}
    db.setdefault("items", [])
    db.setdefault("pending_read", [])
    db.setdefault("pending_reply", [])
    db.setdefault("pending_send", [])
    db.setdefault("pending_control", [])
    db.setdefault("pending_history", [])
    db.setdefault("muted_channels", [])
    db.setdefault("notify_policy", {})
    db.setdefault("threads", {})
    if not isinstance(db.get("taken"), list):
        db["taken"] = []
    db.setdefault("updated", "")
    return db


def save(db: dict) -> dict:
    return _wstore().save(WIDGET_ID, db)


def _renumber(items: list) -> list:
    for i, it in enumerate(items, 1):
        it["n"] = i
    return items


def _key(it: dict) -> dict:
    return {"platform": it.get("platform"), "chatId": it.get("chatId"),
            "messageId": it.get("messageId"), "senderId": it.get("senderId")}


# ── Writes by connectors ────────────────────────────────────────────────────
def set_platform_status(platform: str, status: str, qr=None, detail=None) -> dict:
    """Link state for ONE platform (off | no_creds | starting | connecting | connected | error). `qr` is a PNG
    data-URI or None. `detail` = HUMAN message for the user (what is happening or why it failed) — the widget shows
    it below the loader / in the error card. Does not touch other platforms or the item list."""
    db = load()
    cur = (db.get("platforms") or {}).get(platform) or {}
    if cur.get("status") == status and cur.get("qr") == qr and cur.get("detail") == detail:
        return db      # NO real change (e.g. "Waiting for scan" poll repeats same state) -> do not re-save:
                       # bumping `updated` every second would defeat widgets/store.py's change-gate and flood SSE.
    db["platforms"][platform] = {"status": status, "qr": qr, "detail": detail}
    db["updated"] = _now()
    return save(db)


def upsert_items(platform: str, new_items: list[dict]) -> dict:
    """Add already-triaged items from `platform` to the common list (dedupe by (platform, messageId)) and re-sort by
    urgency. Normalize from the raw triage verdict (senderName/chatName) to the store shape. Skip items from muted
    channels (muted_channels) so they never enter the store."""
    db = load()
    muted_keys = {(m.get("platform"), str(m.get("chatId")))
                  for m in db.get("muted_channels", [])}
    items = db["items"]
    have = {(it.get("platform"), it.get("messageId")) for it in items}
    added = False
    fresh: list[dict] = []      # truly NEW items, to dump into memory (V2-003 · T57)
    # V2-607 — the ledger too, not only the current list: a message the operator DISMISSED is gone from `items`
    # but still unread at the provider, so without this it walks back in on the next connect.
    for m in new_among(db, platform, new_items):
        key = (platform, m.get("messageId"))
        if key in have:         # duplicate WITHIN this batch (new_among only knows the stored state)
            continue
        # Skip muted channels (they do not enter the store)
        if (platform, str(m.get("chatId"))) in muted_keys:
            continue
        have.add(key)
        added = True
        entry = {
            "platform": platform,
            "messageId": m.get("messageId"), "chatId": m.get("chatId"), "senderId": m.get("senderId"),
            "from": m.get("from") or m.get("senderName") or "?",
            "group": m.get("group") or (m.get("chatName") if m.get("isGroup") else None),
            "isGroup": bool(m.get("isGroup")),
            "body": m.get("body", ""), "urgencia": m.get("urgencia", "media"),
            "dirigido_a_mi": bool(m.get("dirigido_a_mi")), "motivo": m.get("motivo", ""),
        }
        # EMAIL metadata to enable threaded REPLIES (V2-051): subject + RFC Message-ID. Only email carries these;
        # other platforms ignore them (optional fields).
        if m.get("subject") is not None:
            entry["subject"] = m.get("subject")
        if m.get("msgid"):
            entry["msgid"] = m.get("msgid")
        # V2-680 — the ORIGINAL's other recipients, which is the only thing that makes a reply-ALL real.
        # Email-only, like the two fields above; a platform that does not send it stores nothing and the
        # widget then does not offer the choice at all.
        if m.get("recipients"):
            entry["recipients"] = [str(a) for a in m.get("recipients") if str(a).strip()][:25]
        # V2-543 — media + real timestamp. The store had "no timestamp" written as a known gap since V2-051
        # ("most recent by appearance order"); connectors send it now and the widget shows real times.
        try:
            entry["ts"] = float(m.get("timestamp") or time.time())
        except (TypeError, ValueError):
            entry["ts"] = time.time()
        if m.get("hasMedia") or m.get("mediaUrls"):
            withm = with_media(m)
            entry["mediaType"] = withm.get("mediaType", "")
            if withm.get("media"):
                entry["media"] = withm["media"]
        items.append(entry)
        fresh.append(entry)
    if not added:
        return db      # nothing new to triage -> do not re-save (avoids `updated` bump + emit from unchanged poll)
    # The same message ALSO joins its conversation (V2-546). The inbox and the thread answer different questions —
    # "what still wants my attention" vs "what was said here" — so reading an item empties the first and leaves
    # the second intact. Before this, reading a message deleted the only copy of it.
    _th = _thread()
    for entry in fresh:
        try:
            _th.append(db, platform, entry.get("chatId"), entry, "in",
                       name=entry.get("group") or entry.get("from") or "")
        except Exception:
            continue
    try:
        _th.prune(db)
    except Exception:
        pass
    # Urgency first, newest first within the same urgency (ts=0 for legacy rows keeps them at the tail).
    items.sort(key=lambda it: (_RANK.get(it.get("urgencia"), 3), -float(it.get("ts") or 0)))
    db["items"] = items
    # Record what was taken in, so a restart (or a dismissal) does not let it back through — V2-607.
    db["taken"] = ([str(k) for k in (db.get("taken") or [])]
                   + [_taken_key(platform, e.get("messageId")) for e in fresh])[-TAKEN_CAP:]
    db["updated"] = _now()
    out = save(db)     # UI SSE intact: the per-widget store still sends the face
    _to_memory(fresh)  # ALSO, durable content goes to central memory (brain recall)
    _to_archive(fresh)  # AND the canonical communications log (V2-628) — the only copy that does not expire
    _to_directory(platform, fresh)   # AND the contact learns the channel he wrote from (V2-683)
    return out


# ── Operator actions (widget / voice) ───────────────────────────────────────
def clear() -> dict:
    """Mark EVERYTHING visible as read (enqueue each key with its platform) and clear the list."""
    db = load()
    for it in db.get("items", []):
        db.setdefault("pending_read", []).append(_key(it))
    db["items"] = []
    db["updated"] = _now()
    return save(db)


# The siblings import this module back at their bottom, so they come AFTER every name they read here.
from connectors.messaging.store.media import (  # noqa: E402,F401
    _KIND_BY_EXT, _media_dir, _media_entries, kind_of, media_refs, sendable, with_media)
from connectors.messaging.store.taken import TAKEN_CAP, _taken_key, new_among, taken_ids  # noqa: E402,F401
from connectors.messaging.store.fanout import _to_archive, _to_directory, _to_memory  # noqa: E402,F401
from connectors.messaging.store.sync import (  # noqa: E402,F401
    CHAT_INDEX_MAX, _CHAT_FIELDS, _clear_chat_items, add_chats, add_history, apply_external_read, record_outbound)
from connectors.messaging.store.queues import (  # noqa: E402,F401
    requeue_pending_read, take_control, take_pending_chats, take_pending_disposal, take_pending_fetch,
    take_pending_group, take_pending_history, take_pending_read, take_pending_reply, take_pending_send,
    take_pending_unread)
