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
        "pending_control": [],
        "muted_channels": [],
    }


def _wstore():
    # lazy: do not couple messaging import-time to the widgets domain (2026-07-17 modularity audit)
    from widgets import store
    return store


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
    db.setdefault("muted_channels", [])
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
        items.append(entry)
        fresh.append(entry)
    if not added:
        return db      # nothing new to triage -> do not re-save (avoids `updated` bump + emit from unchanged poll)
    items.sort(key=lambda it: _RANK.get(it.get("urgencia"), 3))
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


def take_pending_reply(platform: str | None = None) -> list[dict]:
    """Return (and REMOVE) pending replies to send; if `platform` is given, only its own. Each send-capable connector
    (email today) calls with its platform, sends in its app, and if it fails, re-enqueues.
    Cada orden: {platform, chatId, to, messageId, subject, msgid, text}."""
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
