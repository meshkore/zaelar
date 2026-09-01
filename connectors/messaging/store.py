#
# store.py — the UNIFIED messaging store (INI-015). ONE file (widgets/_data/mensajeria.json) where ALL connectors
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
import os
import re
import shutil
import time

WIDGET_ID = "mensajeria"
PLATFORMS = ("whatsapp", "telegram", "email")  # email: V2-051 (IMAP/SMTP, same unified shape)
_RANK = {"alta": 0, "media": 1, "baja": 2}

# ── MEDIA (V2-543) ──────────────────────────────────────────────────────────
# The WhatsApp bridge has downloaded every image/video/audio/document to disk since day one and pushed the
# absolute paths in `mediaUrls` — this whitelist was the single line where they died (measured 2026-09-01:
# the strings mediaUrls/hasMedia/mediaType appeared in bridge.js and NOWHERE in Python). To be visible, a
# file must live DIRECTLY in the widget's own data dir (`widgets/_data/mensajeria/`): that is the only place
# `GET /widgets/mensajeria/asset/{name}` serves, and its namespace is FLAT (basename-only, path-safe).
_MEDIA_MAX_PER_MSG = 6
_MEDIA_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _media_dir() -> str:
    from widgets import store
    return store.data_dir(WIDGET_ID)


def _media_entries(m: dict) -> list[dict]:
    """Local media paths → asset URLs the widget can render. A file already inside the widget's data dir is
    referenced in place; one elsewhere (e.g. a legacy ~/.hermes cache from an old bridge process) is COPIED
    in. Best-effort per file: a missing/unreadable file is skipped, never an error — the message must land
    with or without its picture."""
    urls: list[dict] = []
    mtype = str(m.get("mediaType") or "")
    for path in (m.get("mediaUrls") or [])[:_MEDIA_MAX_PER_MSG]:
        try:
            p = str(path or "")
            if not p or not os.path.isfile(p):
                continue
            name = _MEDIA_SAFE.sub("", os.path.basename(p))
            if not name:
                continue
            dest_dir = _media_dir()
            dest = os.path.join(dest_dir, name)
            if os.path.abspath(os.path.dirname(p)) != os.path.abspath(dest_dir):
                if not os.path.isfile(dest):
                    shutil.copy2(p, dest)
            urls.append({"url": f"/widgets/{WIDGET_ID}/asset/{name}", "type": mtype, "name": name})
        except Exception:
            continue
    return urls


def _now() -> str:
    return time.strftime("%H:%M:%S")


def _empty() -> dict:
    return {
        "platforms": {p: {"status": "off", "qr": None} for p in PLATFORMS},
        "updated": "",
        "items": [],
        "pending_read": [],
        "pending_reply": [],
        "pending_control": [],
        "pending_history": [],
        "muted_channels": [],
        "notify_policy": {},
        "threads": {},
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
    db.setdefault("pending_control", [])
    db.setdefault("pending_history", [])
    db.setdefault("muted_channels", [])
    db.setdefault("notify_policy", {})
    db.setdefault("threads", {})
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
    for m in new_items:
        key = (platform, m.get("messageId"))
        if key[1] is None or key in have:
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
        # V2-543 — media + real timestamp. The store had "no timestamp" written as a known gap since V2-051
        # ("most recent by appearance order"); connectors send it now and the widget shows real times.
        try:
            entry["ts"] = float(m.get("timestamp") or time.time())
        except (TypeError, ValueError):
            entry["ts"] = time.time()
        if m.get("hasMedia") or m.get("mediaUrls"):
            entry["mediaType"] = str(m.get("mediaType") or "")
            media = _media_entries(m)
            if media:
                entry["media"] = media
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
    db["updated"] = _now()
    out = save(db)     # UI SSE intact: the per-widget store still sends the face
    _to_memory(fresh)  # ALSO, durable content goes to central memory (brain recall)
    return out


def _to_memory(items: list[dict]) -> None:
    """Dump inbound messages into central memory as `kind='msg'` memories at `short` level (V2-003 · T57).
    Fire-and-forget through the memory queue; best-effort — a failure here does NOT affect the UI store or triage.
    The per-widget store remains for UI state; memory is for recall.

    Goes through `memory.ingest_message` (the unified TYPED path, multi-source 2026-07-10): indexes `source`
    (platform) + `entity` (sender) in `meta` -> the brain can query BY TYPE with `recent_by_source`, without the
    retriever. `trust='external'` = owner's personal connector."""
    if not items:
        return
    try:
        from memory import api as memapi
    except Exception:
        return
    for it in items:
        try:
            body = (it.get("body") or "").strip()
            if not body:
                continue
            memapi.ingest_message(it.get("platform") or "?", it.get("from") or "?", body,
                                  group=it.get("group"), directed=bool(it.get("dirigido_a_mi")),
                                  trust="external")
        except Exception:
            continue


# ── The world moved without us (V2-546) ─────────────────────────────────────
# The operator answers from his own phone, or reads a chat there. Until now the widget could not know: every
# connector was wired INBOUND-ONLY and read state travelled one way (widget → app). So a conversation he had
# already dealt with kept sitting in the list looking pending, which is exactly the report that opened this.
def record_outbound(platform: str, chat_id, msg: dict, name: str = "") -> dict:
    """A message the OPERATOR sent — from his real app, or from here. It joins the conversation and NEVER the
    inbox: his own words are context, not something demanding his attention.

    Sending in a chat is also the strongest possible evidence that he has SEEN it, so it clears that chat's
    pending items. That is the difference between a widget that mirrors his messaging and one that argues with
    it. The items are dropped WITHOUT enqueuing mark-read: the app they came from already knows."""
    db = load()
    th = _thread()
    added = th.append(db, platform, chat_id, msg, "out", name=name)
    try:
        ts = float(msg.get("ts") or msg.get("timestamp") or time.time())
    except (TypeError, ValueError):
        ts = time.time()
    cleared = _clear_chat_items(db, platform, chat_id, upto_ts=ts)
    marked = th.mark_read(db, platform, chat_id, upto_ts=ts)
    if not (added or cleared or marked):
        return db
    db["updated"] = _now()
    return save(db)


def apply_external_read(platform: str, chat_id, upto_ts: float | None = None, ids=None) -> dict:
    """The operator read this chat somewhere else. Reflect it: clear its pending items and mark the conversation
    read up to that point. Like record_outbound, this does NOT enqueue mark-read — telling the app something it
    just told us would be a loop, and the whole point is that IT is the source of truth here."""
    db = load()
    cleared = _clear_chat_items(db, platform, chat_id, upto_ts=upto_ts, ids=ids)
    marked = _thread().mark_read(db, platform, chat_id, upto_ts=upto_ts, ids=ids)
    if not (cleared or marked):
        return db
    db["updated"] = _now()
    return save(db)


def _clear_chat_items(db: dict, platform: str, chat_id, upto_ts: float | None = None, ids=None) -> int:
    """Drop pending inbox items of one chat that the operator has already handled elsewhere. Bounded by the
    same watermark the platform gave us: a read receipt says "up to here", and dropping messages that arrived
    AFTER it would hide mail he has genuinely not seen."""
    want = {str(i) for i in (ids or [])}
    keep, gone = [], 0
    for it in db.get("items", []):
        same = it.get("platform") == platform and str(it.get("chatId")) == str(chat_id)
        if same and want and str(it.get("messageId")) not in want:
            same = False
        if same and upto_ts is not None and float(it.get("ts") or 0) > float(upto_ts):
            same = False
        if same:
            gone += 1
        else:
            keep.append(it)
    if gone:
        db["items"] = keep
    return gone


def add_history(platform: str, chat_id, msgs: list[dict], complete: bool = False) -> dict:
    """Older messages a connector fetched on demand ("load previous"). Prepends into the conversation and marks
    whether we have now reached its beginning."""
    db = load()
    added = _thread().prepend(db, platform, chat_id, msgs or [], complete=complete)
    db["updated"] = _now()
    return save(db) if (added or complete) else db


def take_pending_history(platform: str | None = None) -> list[dict]:
    """Return (and REMOVE) 'load previous' orders enqueued by the widget: {platform, chatId, beforeTs, beforeId,
    limit}. Same drain contract as the other queues."""
    db = load()
    pending = db.get("pending_history", [])
    if platform is None:
        mine, rest = list(pending), []
    else:
        mine = [k for k in pending if k.get("platform") == platform]
        rest = [k for k in pending if k.get("platform") != platform]
    if pending:
        db["pending_history"] = rest
        save(db)
    return mine


# ── pending_read drain by connectors ────────────────────────────────────────
def take_pending_read(platform: str | None = None) -> list[dict]:
    """Return (and REMOVE) pending_read keys; if `platform` is given, only its own. Each connector calls with its
    platform, marks read in its app, and if it fails, re-enqueues with requeue_pending_read()."""
    db = load()
    pending = db.get("pending_read", [])
    if platform is None:
        mine, rest = list(pending), []
    else:
        mine = [k for k in pending if k.get("platform") == platform]
        rest = [k for k in pending if k.get("platform") != platform]
    db["pending_read"] = rest
    save(db)
    return mine


def take_pending_disposal(kind: str, platform: str | None = None) -> list[dict]:
    """Return (and REMOVE) pending archive/trash keys (V2-543). `kind` in ('archive','trash') → the store keys
    `pending_archive`/`pending_trash`, enqueued by the widget's actions and drained through the owner into the
    bus (msg.archive / msg.trash), where the platform's connector executes them for real."""
    field = f"pending_{kind}"
    db = load()
    pending = db.get(field, [])
    if platform is None:
        mine, rest = list(pending), []
    else:
        mine = [k for k in pending if k.get("platform") == platform]
        rest = [k for k in pending if k.get("platform") != platform]
    if pending:
        db[field] = rest
        save(db)
    return mine


def take_pending_reply(platform: str | None = None) -> list[dict]:
    """Return (and REMOVE) pending replies to send; if `platform` is given, only its own. Each send-capable connector
    (email today) calls with its platform, sends in its app, and if it fails, re-enqueues.
    Each order: {platform, chatId, to, messageId, subject, msgid, text}."""
    db = load()
    pending = db.get("pending_reply", [])
    if platform is None:
        mine, rest = list(pending), []
    else:
        mine = [k for k in pending if k.get("platform") == platform]
        rest = [k for k in pending if k.get("platform") != platform]
    db["pending_reply"] = rest
    save(db)
    return mine


def take_control() -> list[dict]:
    """Return (and REMOVE) control orders enqueued by the WIDGET (connect/disconnect). Drained by the supervisor.
    Each order: {platform, cmd:"connect"|"disconnect", api_id?, api_hash?, forget?}. Removing them from the store
    means secrets (api_hash) do NOT remain resident in the message file (they go to config/connectors.json)."""
    db = load()
    cmds = list(db.get("pending_control", []))
    if cmds:
        db["pending_control"] = []
        save(db)
    return cmds


def requeue_pending_read(keys: list[dict]) -> dict:
    """Re-enqueue keys whose mark-read failed (retry on the next tick). Idempotent."""
    if not keys:
        return load()
    db = load()
    pending = db.get("pending_read", [])
    have = {(k.get("platform"), k.get("chatId"), k.get("messageId")) for k in pending}
    for k in keys:
        sig = (k.get("platform"), k.get("chatId"), k.get("messageId"))
        if sig not in have:
            have.add(sig)
            pending.append(k)
    db["pending_read"] = pending
    return save(db)


# ── Operator actions (widget / voice) ───────────────────────────────────────
def remove_item(n: int, mark_read: bool = True) -> dict:
    """Remove item number `n` (numbering by current order). If mark_read, enqueue its key (with platform) in
    pending_read so the right connector marks it read in its app."""
    db = load()
    items = _renumber(db.get("items", []))
    keep, hit = [], None
    for it in items:
        if it.get("n") == n:
            hit = it
        else:
            keep.append(it)
    if hit and mark_read:
        db.setdefault("pending_read", []).append(_key(hit))
    db["items"] = keep
    db["updated"] = _now()
    return save(db)


def clear() -> dict:
    """Mark EVERYTHING visible as read (enqueue each key with its platform) and clear the list."""
    db = load()
    for it in db.get("items", []):
        db.setdefault("pending_read", []).append(_key(it))
    db["items"] = []
    db["updated"] = _now()
    return save(db)
