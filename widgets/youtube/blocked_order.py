"""A pasted link from a channel he blocked: the order wins, and the turn's reply owes him the word (V2-604).

`video-blocked-channel-respected` (2026-10-14, ES and EN 3/5): the link played — or was queued — and neither reply
said it came from the channel he had blocked a minute earlier. The card's own `explicit_link_notice` wrote its
banner and handed the model a `message`; the model did not say it, and `add` (the ES round's «ponme este») wrote
nothing at all. This module is the FACT the receipt reads: the action that let a blocked channel's link through
stamps it on the card's store, and `take` hands it — once — to `nucleo.flash.blocked_channel_receipt`, which says it
in the reply in his language on both channels.
"""
from __future__ import annotations

import time

_KEY = "blocked_order"
#: Older than this, the stamp belongs to a turn that is over (the voice rail dispatches detached: ~1 s is normal).
MAX_AGE_S = 90.0


def stamp(db: dict, channel: str, title: str, queued: bool) -> None:
    """Record that an explicit order let `channel` (blocked) through: `queued` for an add, else it plays."""
    db[_KEY] = {"channel": str(channel or "")[:80], "title": str(title or "")[:100],
                "queued": bool(queued), "at": time.time()}


def take(max_age_s: float = MAX_AGE_S) -> dict:
    """The pending stamp, consumed — `{}` when there is none or it is stale. Reads and writes the card's store."""
    from widgets import store
    db = store.load("youtube") or {}
    got = db.get(_KEY) if isinstance(db.get(_KEY), dict) else {}
    if not got:
        return {}
    db.pop(_KEY, None)
    store.save("youtube", db)
    fresh = time.time() - float(got.get("at") or 0) <= max_age_s
    return got if fresh and got.get("channel") else {}


def pending() -> bool:
    """Is a stamp waiting (without consuming it)?"""
    from widgets import store
    return isinstance((store.load("youtube") or {}).get(_KEY), dict)
