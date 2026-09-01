#
# thread.py — the CONVERSATION store of the messaging widget (V2-546). Until this existed, the widget held ONE
# list: `items`, the pending inbox. Reading or dismissing a message REMOVED it, so there was no history at all —
# opening a chat showed the unread messages and nothing else, and a reply the operator sent from his own phone had
# nowhere to be recorded.
#
# WHERE THIS LIVES, and why it is not in `connectors/messaging/`: the widget contract keeps `data.py` stdlib-only
# plus the `widgets` package, so the widget may NOT import `connectors`. Connectors, on the other hand, already
# import `widgets.store`. Putting the rules here is the only placement where BOTH sides read the same code — and
# these rules (cap, ordering, dedup, read watermark) are exactly the kind that rot when they exist twice.
#
# Shape, inside the same store file the rest of the widget uses:
#   db["threads"] = { "<platform>|<chatId>": {
#       "name": str,                # display name of the chat, best known
#       "msgs": [ {id, dir, who, body, ts, read, mediaType?, media?} ],   # OLDEST first
#       "complete": bool,           # true only once a history fetch proved there is nothing older
#       "touched": float,           # last write, for pruning
#   } }
#
# `dir` is "in" (someone wrote to us) or "out" (the operator wrote, from here or from his own app). An "out"
# message is never unread and never enters the inbox: it is context, not something demanding attention.
#
import os
import time

# The operator's ask was "at least 20 messages per chat that stay there for days". These are the ceilings of a
# single JSON file that is rewritten on every save, so they are bounded on THREE axes: per chat, per age, and
# total number of chats — an unbounded any of them turns a message store into a slowly growing disk problem.
KEEP = max(1, int(os.getenv("MSG_THREAD_KEEP", "40") or 40))
DAYS = max(1, int(os.getenv("MSG_THREAD_DAYS", "14") or 14))
MAX_THREADS = max(1, int(os.getenv("MSG_THREAD_MAX", "80") or 80))

_OUT_LABEL = "Tú"


def key(platform, chat_id) -> str:
    return f"{platform}|{chat_id}"


def _threads(db: dict) -> dict:
    t = db.get("threads")
    if not isinstance(t, dict):
        t = {}
        db["threads"] = t
    return t


def _thread(db: dict, platform, chat_id, *, create: bool = True) -> dict | None:
    th = _threads(db)
    k = key(platform, chat_id)
    cur = th.get(k)
    if not isinstance(cur, dict):
        if not create:
            return None
        cur = {"name": "", "msgs": [], "complete": False, "touched": time.time()}
        th[k] = cur
    if not isinstance(cur.get("msgs"), list):
        cur["msgs"] = []
    return cur


def _norm(m: dict, direction: str) -> dict:
    """One message of a conversation, normalized. An OUT message is born read: the operator wrote it."""
    out = {
        "id": str(m.get("messageId") if m.get("messageId") is not None else m.get("id") or ""),
        "dir": "out" if direction == "out" else "in",
        "who": (m.get("from") or m.get("senderName") or (_OUT_LABEL if direction == "out" else "?")),
        "body": m.get("body") or "",
        "read": True if direction == "out" else bool(m.get("read")),
    }
    try:
        out["ts"] = float(m.get("ts") or m.get("timestamp") or time.time())
    except (TypeError, ValueError):
        out["ts"] = time.time()
    if m.get("mediaType"):
        out["mediaType"] = str(m.get("mediaType"))
    if m.get("media"):
        out["media"] = m.get("media")
    return out


def append(db: dict, platform, chat_id, msg: dict, direction: str = "in", name: str = "") -> bool:
    """Add ONE message to a conversation. Idempotent by id — the same message arriving twice (a connector
    retrying, a mark-read echo) must not duplicate the thread. Returns True if it was actually added.

    Insertion respects TIME, not arrival: an "out" message captured from the operator's phone can reach us after
    a later inbound one, and a thread that is out of order reads as a different conversation."""
    entry = _norm(msg, direction)
    if not entry["id"]:
        return False
    th = _thread(db, platform, chat_id)
    msgs = th["msgs"]
    for i, prev in enumerate(msgs):
        if prev.get("id") == entry["id"]:
            # Same message again: keep the read state we already had (a later re-delivery must not
            # resurrect an unread mark the operator already cleared) but let content/media fill in.
            entry["read"] = bool(prev.get("read")) or entry["read"]
            msgs[i] = entry
            th["touched"] = time.time()
            return False
    pos = len(msgs)
    while pos > 0 and float(msgs[pos - 1].get("ts") or 0) > entry["ts"]:
        pos -= 1
    msgs.insert(pos, entry)
    if len(msgs) > KEEP:
        # Dropping the oldest means we no longer hold the start of the conversation, whatever we believed
        # before — saying otherwise would make the widget claim there is nothing older when there is.
        del msgs[0:len(msgs) - KEEP]
        th["complete"] = False
    if name:
        th["name"] = name
    th["touched"] = time.time()
    return True


def prepend(db: dict, platform, chat_id, msgs: list[dict], complete: bool = False) -> int:
    """Add OLDER messages fetched on demand ("load previous"). `complete` = the source proved there is nothing
    before these, so the widget can stop offering the button. Returns how many were genuinely new."""
    th = _thread(db, platform, chat_id)
    have = {m.get("id") for m in th["msgs"]}
    added = 0
    for m in msgs or []:
        entry = _norm(m, m.get("dir") or "in")
        if not entry["id"] or entry["id"] in have:
            continue
        have.add(entry["id"])
        th["msgs"].append(entry)
        added += 1
    th["msgs"].sort(key=lambda m: float(m.get("ts") or 0))
    # A "load previous" may legitimately push us past the live cap; the ceiling that matters for disk is the
    # one applied on the way IN, and truncating here would delete what the operator just asked to see.
    over = len(th["msgs"]) - (KEEP * 2)
    if over > 0:
        del th["msgs"][0:over]
        complete = False
    th["complete"] = bool(complete)
    th["touched"] = time.time()
    return added


def mark_read(db: dict, platform, chat_id, upto_ts: float | None = None, ids=None) -> int:
    """Mark inbound messages of this chat as read. With `upto_ts`, everything up to that instant (the shape every
    platform's read receipt has: a watermark, not a list). With `ids`, only those. With neither, the whole chat."""
    th = _thread(db, platform, chat_id, create=False)
    if th is None:
        return 0
    want = {str(i) for i in (ids or [])}
    n = 0
    for m in th["msgs"]:
        if m.get("dir") != "in" or m.get("read"):
            continue
        if want and m.get("id") not in want:
            continue
        if upto_ts is not None and float(m.get("ts") or 0) > float(upto_ts):
            continue
        m["read"] = True
        n += 1
    if n:
        th["touched"] = time.time()
    return n


def window(db: dict, platform, chat_id) -> list[dict]:
    """The conversation as it should be displayed: oldest first."""
    th = _thread(db, platform, chat_id, create=False)
    return list(th["msgs"]) if th else []


def meta(db: dict, platform, chat_id) -> dict:
    """What the widget needs to draw the boundary honestly: where our copy starts, and whether there is any point
    offering to load more. `complete` false with zero messages is NOT an invitation — there is no chat yet."""
    th = _thread(db, platform, chat_id, create=False)
    if th is None or not th["msgs"]:
        return {"count": 0, "oldest_ts": 0, "complete": False, "can_load_more": False}
    return {
        "count": len(th["msgs"]),
        "oldest_ts": float(th["msgs"][0].get("ts") or 0),
        "oldest_id": th["msgs"][0].get("id") or "",
        "complete": bool(th.get("complete")),
        "can_load_more": not bool(th.get("complete")),
    }


def unread(db: dict, platform, chat_id) -> int:
    th = _thread(db, platform, chat_id, create=False)
    if th is None:
        return 0
    return sum(1 for m in th["msgs"] if m.get("dir") == "in" and not m.get("read"))


def prune(db: dict, now: float | None = None) -> int:
    """Drop conversations nobody has touched in DAYS, then cap the total. Returns how many were dropped."""
    th = _threads(db)
    now = time.time() if now is None else now
    cutoff = now - DAYS * 86400
    dead = [k for k, v in th.items() if float((v or {}).get("touched") or 0) < cutoff]
    for k in dead:
        th.pop(k, None)
    if len(th) > MAX_THREADS:
        order = sorted(th.items(), key=lambda kv: float((kv[1] or {}).get("touched") or 0))
        for k, _ in order[0:len(th) - MAX_THREADS]:
            th.pop(k, None)
            dead.append(k)
    return len(dead)
