# The world moved without us (V2-546) — what a connector reports BACK about the operator's own app.
#
# The operator answers from his own phone, or reads a chat there. Until now the widget could not know: every
# connector was wired INBOUND-ONLY and read state travelled one way (widget → app). So a conversation he had
# already dealt with kept sitting in the list looking pending, which is exactly the report that opened this.
# Same door for the pages he asks for afterwards: older messages of a chat and the chat list itself.
import time


def record_outbound(platform: str, chat_id, msg: dict, name: str = "") -> dict:
    """A message the OPERATOR sent — from his real app, or from here. It joins the conversation and NEVER the
    inbox: his own words are context, not something demanding his attention.

    Sending in a chat is also the strongest possible evidence that he has SEEN it, so it clears that chat's
    pending items. That is the difference between a widget that mirrors his messaging and one that argues with
    it. The items are dropped WITHOUT enqueuing mark-read: the app they came from already knows."""
    db = _svc.load()
    th = _svc._thread()
    msg = _svc.with_media(msg)
    added = th.append(db, platform, chat_id, msg, "out", name=name)
    _svc._to_archive([msg], platform, chat_id, direction="out", chat_name=name)
    try:
        ts = float(msg.get("ts") or msg.get("timestamp") or time.time())
    except (TypeError, ValueError):
        ts = time.time()
    cleared = _clear_chat_items(db, platform, chat_id, upto_ts=ts)
    marked = th.mark_read(db, platform, chat_id, upto_ts=ts)
    if not (added or cleared or marked):
        return db
    db["updated"] = _svc._now()
    return _svc.save(db)


def apply_external_read(platform: str, chat_id, upto_ts: float | None = None, ids=None) -> dict:
    """The operator read this chat somewhere else. Reflect it: clear its pending items and mark the conversation
    read up to that point. Like record_outbound, this does NOT enqueue mark-read — telling the app something it
    just told us would be a loop, and the whole point is that IT is the source of truth here."""
    db = _svc.load()
    cleared = _clear_chat_items(db, platform, chat_id, upto_ts=upto_ts, ids=ids)
    marked = _svc._thread().mark_read(db, platform, chat_id, upto_ts=upto_ts, ids=ids)
    # The chat list's counter came from the app; a whole-chat read there zeroes it here too.
    row = (((db.get("chat_index") or {}).get(platform) or {}).get("rows") or {}).get(str(chat_id))
    if row and upto_ts is None and not ids and row.get("unread"):
        row["unread"] = 0
        marked = marked or 1
    if not (cleared or marked):
        return db
    db["updated"] = _svc._now()
    return _svc.save(db)


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


def add_history(platform: str, chat_id, msgs: list[dict], complete: bool = False,
                name: str = "", is_group=None) -> dict:
    """Older messages a connector fetched on demand ("load previous"). Prepends into the conversation and marks
    whether we have now reached its beginning.

    V2-624 — `name`/`is_group` label a thread BORN from a platform-wide fetch (msg.fetch): without them a
    freshly-pulled group would be named after whichever member spoke first. Only set what arrives; a name a
    live inbound message already wrote is never overwritten by an empty one."""
    db = _svc.load()
    th = _svc._thread()
    added = th.prepend(db, platform, chat_id, msgs or [], complete=complete)
    _svc._to_archive(msgs or [], platform, chat_id, chat_name=name, is_group=is_group)
    if name or is_group is not None:
        cur = (db.get("threads") or {}).get(th.key(platform, chat_id))
        if isinstance(cur, dict):
            if name and not cur.get("name"):
                cur["name"] = str(name)
            if is_group:
                cur["isGroup"] = True
    db["updated"] = _svc._now()
    return _svc.save(db) if (added or complete or name or is_group is not None) else db


#: Rows kept per platform in the chat index. Enough for months of an active account; the oldest go first.
CHAT_INDEX_MAX = 600
_CHAT_FIELDS = ("name", "kind", "unread", "ts", "preview", "mediaType", "fromMe", "archived", "pinned", "muted",
                "forum", "lastId")


def add_chats(platform: str, ev: dict) -> dict:
    """Fold one page of a connector's chat list into `chat_index[platform]`.

    The cursor only moves when the page answered IS the deepest one asked for: a refresh of the first page (on
    entering the platform again) must not throw away the pages the operator already walked back through."""
    db = _svc.load()
    idx = db.setdefault("chat_index", {}).setdefault(platform, {})
    rows = idx.setdefault("rows", {})
    incoming = list(ev.get("chats") or [])
    if ev.get("before") is None and not idx.get("archive_seeded"):
        # Once per platform: what the archive already holds fills in what the connector can no longer list.
        # Connector rows go AFTER, so a name or counter the app sent wins over the archive's.
        try:
            from connectors.messaging import archive
            incoming = archive.chats(platform) + incoming
            idx["archive_seeded"] = True
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger("zaelar.messaging.store").warning(f"chat list archive seed: {type(e).__name__}")
    for c in incoming:
        cid = str(c.get("chatId") or "").strip()
        if not cid:
            continue
        row = dict(rows.get(cid) or {})
        newer = float(c.get("ts") or 0) >= float(row.get("ts") or 0)
        for k in _CHAT_FIELDS:
            if k not in c or c[k] is None or c[k] == "":
                continue
            if k in ("ts", "preview", "mediaType", "fromMe", "lastId") and not newer:
                continue                     # the last message only moves forward
            row[k] = c[k]
        row["chatId"] = cid
        rows[cid] = row
    if len(rows) > CHAT_INDEX_MAX:
        keep = sorted(rows.values(), key=lambda r: -float(r.get("ts") or 0))[:CHAT_INDEX_MAX]
        idx["rows"] = {r["chatId"]: r for r in keep}
    before, cursor = ev.get("before"), idx.get("cursor")
    if (before is None and cursor is None) or (before is not None and before == cursor):
        idx["cursor"] = ev.get("nextBefore")
        idx["complete"] = bool(ev.get("complete"))
    elif before is None and ev.get("complete"):
        idx["complete"] = True
    idx["error"] = str(ev.get("error") or "")
    idx["answered_at"] = time.time()
    idx.pop("asked_at", None)
    db["updated"] = _svc._now()
    return _svc.save(db)


# Read back through the facade (V2-778 F1): tests patch `load`/`save`/`_to_archive` there.
from connectors.messaging import store as _svc  # noqa: E402
