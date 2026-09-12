"""A reply the operator has written and not sent yet — one PER CONVERSATION (V2-680).

Extracted from `data.py` rather than raising its ceiling (the house rule: a growing file is paid by
splitting it, never by moving the line). The seam is one-directional: this module knows nothing about the
widget's actions, its store or its numbering — `data.py` resolves the target and does the saving, and hands
the resolved dicts in. Stdlib only, like everything else this widget runs server-side.

Why per conversation: before this the widget held exactly ONE draft, so starting a reply to a second
conversation silently destroyed the first. And why the draft carries its own `recipients`: a reply-ALL has
to copy the people the ORIGINAL went to, and that list is only knowable when the mail was written — after
the item leaves the inbox there is nothing left to read it from.
"""
from __future__ import annotations

import time

MAX = 50

# What travels with a draft so the send can be made without the original item still existing.
_TARGET_FIELDS = ("platform", "chatId", "senderId", "messageId", "subject", "msgid", "n")


def key(target: dict) -> str:
    """Which CONVERSATION (or single mail) a draft belongs to.

    A single email is addressed by its `messageId`, stable for the life of the message; anything else is
    the conversation itself. `n` is deliberately NOT part of this: it is positional and gets reused the
    moment an earlier item leaves the list (`_renumber`), so keying on it would hand one conversation's
    half-written reply to whatever message inherited that number next."""
    mid = target.get("messageId")
    if mid is not None:
        return f"m:{mid}"
    return f"c:{target.get('platform')}:{target.get('chatId')}"


def trim(drafts: dict) -> None:
    """Keep the store bounded. Oldest first, because the one being written is the one just touched.

    Nothing EXPIRES on a clock: an unsent reply is the operator's own unfinished work, and deleting it
    because a week passed would lose something he never asked us to throw away. The cap exists so the
    store cannot grow without limit, not as a retention policy."""
    if len(drafts) <= MAX:
        return
    for k, _ in sorted(drafts.items(), key=lambda kv: kv[1].get("at") or 0)[: len(drafts) - MAX]:
        drafts.pop(k, None)


def write(db: dict, target: dict, text: str, reply_all: bool) -> dict:
    """Store (or clear) the draft for `target`'s conversation. Returns the action's result payload.

    `db["draft"]` stays the MOST RECENT one, unchanged in shape: it is what a voice «envíalo» with no
    conversation named resolves to, and what every older reader of this payload already expects."""
    k = key(target)
    drafts = db.setdefault("drafts", {})
    if not text.strip():
        drafts.pop(k, None)
        if (db.get("draft") or {}).get("key") == k:
            db["draft"] = None
        return {"ok": True, "cleared": True, "key": k}
    entry = {"key": k,
             "text": text[:4000],
             "target": {f: target.get(f) for f in _TARGET_FIELDS},
             "reply_all": bool(reply_all),
             "recipients": [str(a) for a in (target.get("recipients") or []) if str(a).strip()][:25],
             "at": int(time.time())}
    drafts[k] = entry
    trim(drafts)
    db["draft"] = entry
    return {"ok": True, "text": entry["text"], "key": k}


def pick(db: dict, k: str | None) -> dict:
    """The draft a send means: the named conversation's, or the most recent one when nothing is named."""
    drafts = db.get("drafts") or {}
    return (drafts.get(k) if k else None) or db.get("draft") or {}


def forget(db: dict, k: str | None) -> None:
    """Drop the draft that was just sent — and ONLY that one."""
    drafts = db.get("drafts") or {}
    if k:
        drafts.pop(k, None)
    if (db.get("draft") or {}).get("key") in (None, k):
        db["draft"] = None


def cc_for(draft: dict) -> list:
    """Who a send copies: the original's other recipients on a reply-ALL, nobody otherwise.

    A draft written against an item ingested before `recipients` existed carries an empty list, so a
    reply-all over it is an honest plain reply rather than an invented set of addresses."""
    if not draft.get("reply_all"):
        return []
    return [str(a) for a in (draft.get("recipients") or []) if str(a).strip()]
