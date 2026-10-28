# The queues the WIDGET fills and a connector (or the supervisor) DRAINS. Every `take_*` returns the orders and
# REMOVES them in the same synchronous read-modify-write; a failed order is re-enqueued by its drainer.
import time


def take_pending_history(platform: str | None = None) -> list[dict]:
    """Return (and REMOVE) 'load previous' orders enqueued by the widget: {platform, chatId, beforeTs, beforeId,
    limit}. Same drain contract as the other queues."""
    db = _svc.load()
    pending = db.get("pending_history", [])
    if platform is None:
        mine, rest = list(pending), []
    else:
        mine = [k for k in pending if k.get("platform") == platform]
        rest = [k for k in pending if k.get("platform") != platform]
    if pending:
        db["pending_history"] = rest
        _svc.save(db)
    return mine


def take_pending_group() -> list[dict]:
    """Return (and REMOVE) group-creation orders enqueued by the widget's `create_group`."""
    db = _svc.load()
    pending = db.get("pending_group", [])
    if pending:
        db["pending_group"] = []
        _svc.save(db)
    return list(pending)


def take_pending_chats() -> list[dict]:
    """Return (and REMOVE) chat-list page orders: {platform, before, limit}. Enqueued by the widget, published to
    `msg.chats` by the owner, served by that platform's connector."""
    db = _svc.load()
    pending = db.get("pending_chats", [])
    if pending:
        db["pending_chats"] = []
        _svc.save(db)
    return list(pending)


def take_pending_fetch() -> list[dict]:
    """Return (and REMOVE) platform-wide pull orders (V2-624): {platform, since_hours}. Enqueued by the
    widget's `fetch_now`, published to `msg.fetch` by the owner, served by that platform's connector."""
    db = _svc.load()
    pending = db.get("pending_fetch", [])
    if pending:
        db["pending_fetch"] = []
        _svc.save(db)
    return list(pending)


# ── pending_read drain by connectors ────────────────────────────────────────
def take_pending_read(platform: str | None = None) -> list[dict]:
    """Return (and REMOVE) pending_read keys; if `platform` is given, only its own. Each connector calls with its
    platform, marks read in its app, and if it fails, re-enqueues with requeue_pending_read()."""
    db = _svc.load()
    pending = db.get("pending_read", [])
    if platform is None:
        mine, rest = list(pending), []
    else:
        mine = [k for k in pending if k.get("platform") == platform]
        rest = [k for k in pending if k.get("platform") != platform]
    db["pending_read"] = rest
    _svc.save(db)
    return mine


def take_pending_disposal(kind: str, platform: str | None = None) -> list[dict]:
    """Return (and REMOVE) pending archive/trash keys (V2-543). `kind` in ('archive','trash') → the store keys
    `pending_archive`/`pending_trash`, enqueued by the widget's actions and drained through the owner into the
    bus (msg.archive / msg.trash), where the platform's connector executes them for real."""
    field = f"pending_{kind}"
    db = _svc.load()
    pending = db.get(field, [])
    if platform is None:
        mine, rest = list(pending), []
    else:
        mine = [k for k in pending if k.get("platform") == platform]
        rest = [k for k in pending if k.get("platform") != platform]
    if pending:
        db[field] = rest
        _svc.save(db)
    return mine


def take_pending_reply(platform: str | None = None) -> list[dict]:
    """Return (and REMOVE) pending replies to send; if `platform` is given, only its own. Each send-capable connector
    (email today) calls with its platform, sends in its app, and if it fails, re-enqueues.
    Each order: {platform, chatId, to, messageId, subject, msgid, text}."""
    db = _svc.load()
    pending = db.get("pending_reply", [])
    now = time.time()
    due = lambda k: float(k.get("not_before") or 0) <= now   # noqa: E731 — a reply scheduled for later waits (V2-800)
    mine = [k for k in pending if due(k) and (platform is None or k.get("platform") == platform)]
    rest = [k for k in pending if k not in mine]
    db["pending_reply"] = rest
    _svc.save(db)
    return mine


def take_pending_unread() -> list[dict]:
    """Return (and REMOVE) the keys to put back to unread in their app."""
    db = _svc.load()
    mine = list(db.get("pending_unread", []) or [])
    if mine:
        db["pending_unread"] = []
        _svc.save(db)
    return mine


def take_pending_send(platform: str | None = None) -> list[dict]:
    """Return (and REMOVE) pending sends to a PERSON (V2-683) — the sibling of `take_pending_reply` for the
    orders that OPEN a conversation instead of answering one. Each order:
    {ref, platform, to, chatId, name, contactId, text, subject?, objective?}.

    `to` is what the connector needs to open the conversation (a username, a phone, an address) and `chatId`
    is empty until one exists — which is exactly the difference with a reply, and why the connector echoes
    the id it resolved (`connector.msg_out` carrying this `ref`) instead of the caller inventing one."""
    db = _svc.load()
    pending = db.get("pending_send", [])
    now = time.time()
    due = lambda k: float(k.get("not_before") or 0) <= now   # noqa: E731 — an order being typed on screen waits
    if platform is None:
        mine = [k for k in pending if due(k)]
    else:
        mine = [k for k in pending if k.get("platform") == platform and due(k)]
    rest = [k for k in pending if k not in mine]
    if mine:
        db["pending_send"] = rest
        _svc.save(db)
    return mine


def take_control() -> list[dict]:
    """Return (and REMOVE) control orders enqueued by the WIDGET (connect/disconnect). Drained by the supervisor.
    Each order: {platform, cmd:"connect"|"disconnect", api_id?, api_hash?, forget?}. Removing them from the store
    means secrets (api_hash) do NOT remain resident in the message file (they go to config/connectors.json)."""
    db = _svc.load()
    cmds = list(db.get("pending_control", []))
    if cmds:
        db["pending_control"] = []
        _svc.save(db)
    return cmds


def requeue_pending_read(keys: list[dict]) -> dict:
    """Re-enqueue keys whose mark-read failed (retry on the next tick). Idempotent."""
    if not keys:
        return _svc.load()
    db = _svc.load()
    pending = db.get("pending_read", [])
    have = {(k.get("platform"), k.get("chatId"), k.get("messageId")) for k in pending}
    for k in keys:
        sig = (k.get("platform"), k.get("chatId"), k.get("messageId"))
        if sig not in have:
            have.add(sig)
            pending.append(k)
    db["pending_read"] = pending
    return _svc.save(db)


# Read back through the facade (V2-778 F1): tests patch `load`/`save` there.
from connectors.messaging import store as _svc  # noqa: E402
