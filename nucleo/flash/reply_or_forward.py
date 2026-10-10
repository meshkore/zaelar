"""A reply addressed to someone else is a FORWARD (demo pass 110, E3, 2026-10-05).

«send the invoice to quinn, tell him we're already trying inworld» — the model called `mensajeria:reply` on the
Orion receipt with «Hi Quinn — forwarding the Orion receipt…». A reply goes to the message's SENDER: had he
said «yes» to the question the outward gate rightly asked, the note for Quinn would have gone to Orion. When the
verdict is sure it already runs `forward` instead (full12/full18 E3); this pass it read 0.49 and nothing did.

The rule reads data, not phrasing: his sentence names exactly ONE person of the directory, and that person is not
who the reply would reach. Then the act he ordered is the card's `forward` to that person, carrying the same
message. Anything less certain — no one named, two named, the named person IS the sender, a reply whose message
cannot be resolved, a card without `forward` — leaves the model's call as it was.
"""
from __future__ import annotations

import re

_TOK = re.compile(r"[\w.@+-]{3,}")


def _target(db: dict, n):
    """The item `reply` would answer — the same duality `mensajeria.actions._a_reply` resolves."""
    from widgets.mensajeria import data as _d
    if db.get("active_chat") is not None:
        return next((it for it in _d._renumber(db.get("items", [])) if it.get("n") == n), None)
    chat = next((c for c in _d._group_chats(_d._visible_items(db)) if c.get("n") == n), None)
    if not chat:
        return None
    key = (chat["platform"], str(chat["chatId"]))
    msgs = [it for it in db.get("items", []) if (it.get("platform"), str(it.get("chatId"))) == key]
    return msgs[-1] if msgs else None


def _is_him(person: dict, item: dict) -> bool:
    hay = " ".join(str(item.get(k) or "") for k in ("from", "who", "senderId", "chatId")).lower()
    toks = _TOK.findall(" ".join(str(person.get(k) or "") for k in ("name", "email")).lower())
    return any(t in hay for t in toks)


def forward_of(widget_id: str, action: str, payload: dict, said: str) -> dict | None:
    """The `forward` payload this `reply` really is, or None. Never raises."""
    try:
        if (widget_id or "").split("::")[0] != "mensajeria" or action != "reply" or not isinstance(payload, dict):
            return None
        from nucleo.flash import direct_action as _da
        if "contact" not in _da._payload_spec("mensajeria", "forward"):
            return None
        from widgets.contactos import data as _ct
        named = _ct.people_named(said or "")
        if len(named) != 1 or not named[0].get("name"):
            return None
        from widgets.mensajeria import data as _md
        item = _target(_md.load_db(), payload.get("n"))
        if not item or not item.get("messageId") or _is_him(named[0], item):
            return None
        out = {"contact": str(named[0]["name"]), "messageId": str(item["messageId"])}
        return {**out, "text": str(payload["text"])} if str(payload.get("text") or "").strip() else out
    except Exception:  # noqa: BLE001
        return None


def instead(widget_id: str, action: str, payload: dict, said: str) -> str:
    """`"forward"` when the model's `reply` is a forward to the person he named, else `""`."""
    return "forward" if forward_of(widget_id, action, payload, said) else ""
