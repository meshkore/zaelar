"""names.py — every conversation this card shows is named by ONE resolver (V2-819).

The operator, on a WhatsApp chat titled with a bare phone number: that number is in his contacts as «mama». Each
list and header of this card named a conversation its own way — the connector's chat index, the thread's stored
name, the first inbound sender, the chat id's digits — and none of them asked the contacts he already has. The
resolver is `widgets.directory.namer` (contact by conversation, then by phone or address, then the platform's own
display name, then the bare id); this module only walks the view and applies it, once, to every place a
conversation is named. A GROUP keeps its own subject: no contact is a group chat.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.mensajeria.names")


def _namer():
    try:
        from widgets import directory
        return directory.namer()
    except Exception as e:  # noqa: BLE001 — no directory: every name stays what the platform said
        logger.info(f"names: contacts unreadable ({type(e).__name__}: {e})")
        return None


def _apply(name, platform, chat_id, current, row: dict, field: str = "name") -> None:
    got = name(platform, chat_id, current)
    row[field] = got["name"]
    if got.get("photo"):
        row["photo"] = got["photo"]


def rows(chats: list, name=None) -> list:
    """Name a list of conversation rows in place (`platform`, `chatId`, `name`, `isGroup`|`kind`)."""
    name = name or _namer()
    if name is None:
        return chats
    for r in chats or []:
        if not isinstance(r, dict) or r.get("isGroup") or r.get("kind") in ("group", "channel"):
            continue
        _apply(name, r.get("platform"), r.get("chatId"), r.get("name") or "", r)
    return chats


def apply(view: dict) -> dict:
    """Name every conversation in `view_data()`'s payload, in place. Never raises."""
    try:
        name = _namer()
        if name is None:
            return view
        rows(view.get("chats") or [], name)
        rows(view.get("activity_chats") or [], name)
        for platform, lst in (view.get("chat_list") or {}).items():
            for r in (lst or {}).get("rows") or []:
                if isinstance(r, dict):
                    r.setdefault("platform", platform)
            rows((lst or {}).get("rows") or [], name)
        active, meta = view.get("active_chat"), view.get("thread_meta")
        if isinstance(active, dict) and isinstance(meta, dict) and not meta.get("isGroup"):
            items = view.get("active_items") or []
            said = next((it.get("from") for it in items
                         if it.get("dir") != "out" and str(it.get("from") or "").strip() not in ("", "?")), "")
            _apply(name, active.get("platform"), active.get("chatId"), said or meta.get("name") or "", meta)
        # A message's sender in a ONE-TO-ONE chat is the conversation itself: the «completo» profile and the
        # brain's digest read `from`, and it must say the same name as the list above it.
        for it in view.get("items") or []:
            if isinstance(it, dict) and not it.get("isGroup") and it.get("dir") != "out":
                it["from"] = name(it.get("platform"), it.get("chatId"), it.get("from") or "")["name"]
    except Exception as e:  # noqa: BLE001
        logger.info(f"names: view left as the platforms named it ({type(e).__name__}: {e})")
    return view
