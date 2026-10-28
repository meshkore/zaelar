#
# shape.py — the STORE SHAPE of the messaging widget: its id, its three platforms, the empty and the reset state,
# loading the store with every key present, and the numbered list the widget and the brain both read. Moved out of
# data.py (which re-exports every name) with no behaviour change. stdlib plus the `widgets` package, like data.py.
#
from .. import store


WIDGET_ID = "mensajeria"
_PLATFORMS = ("whatsapp", "telegram", "email")   # email: V2-051


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
