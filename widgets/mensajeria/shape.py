#
# shape.py — the STORE SHAPE of the messaging widget: its id, its three platforms, the empty and the reset state,
# loading the store with every key present, and the numbered list the widget and the brain both read. stdlib plus
# the `widgets` package, like data.py (which re-exports every name).
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
    """Blank state for an operator reset (`widgets/reset.py`): messages and queues go, each platform's connection
    state stays — a plain `_empty()` would show every platform «off» while the accounts remain linked."""
    fresh = _empty()
    cur = store.load(WIDGET_ID, {})
    if isinstance(cur.get("platforms"), dict):
        fresh["platforms"] = cur["platforms"]
    # His own CONFIGURATION (autoresponder, view criteria — V2-624) and his unsent DRAFTS (V2-680) survive a reset:
    # a reset clears what arrived, never his settings or his own writing.
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

    Each item carries `highlight` (V2-607): does it meet the SUMMARY tab's criterion (default: addressed to him).
    Nothing is filtered here; computed at read time, so a policy change re-sorts the screen already shown.
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
