"""channels.py — HOW to write to somebody: a contact's channel rows (V2-683, split from `model.py`)."""
from __future__ import annotations

from widgets.contactos.model import norm, platform


# Choosing one lives in `widgets/directory.py`; this file only stores and validates what it is told.


def channel_row(raw) -> dict | None:
    """One channel from whatever shape the caller used. A row with no platform, or with neither a handle nor
    a chatId, is not a channel: it carries no way to reach anybody and storing it would make
    `channel_for` answer «yes, by Telegram» over nothing."""
    if not isinstance(raw, dict):
        return None
    p = platform(raw.get("platform"))
    if not p:
        return None
    handle = str(raw.get("handle") or raw.get("address") or raw.get("phone") or "").strip()
    chat_id = str(raw.get("chatId") or "").strip()
    if not handle and not chat_id:
        return None
    row = {"platform": p, "handle": handle, "chatId": chat_id,
           "source": str(raw.get("source") or "operator").strip() or "operator",
           "volume": int(raw.get("volume") or 0)}
    try:
        row["last_seen"] = float(raw.get("last_seen") or 0)
    except (TypeError, ValueError):
        row["last_seen"] = 0.0
    return row


def channels_in(payload: dict) -> list[dict]:
    """`channels` as a list of rows, or a single `{platform, handle}` — deduped by platform, last one wins."""
    raw = payload.get("channels")
    if raw is None:
        # The FLAT shapes a model reaches for (demo pass 101: `channel: telegram, handle: @x` saved Rowan with
        # no Telegram): one `{channel|platform, handle|chatId}`, or the platform as its own key.
        flat = [{"platform": payload.get("channel") or payload.get("platform"),   # pass 104: or `value`
                 "handle": payload.get("handle") or payload.get("value"), "chatId": payload.get("chatId")}]
        flat += [{"platform": p, "handle": payload.get(p)} for p in ("telegram", "whatsapp")
                 if isinstance(payload.get(p), str) and payload.get(p).strip()]
        raw = flat
    rows = raw if isinstance(raw, (list, tuple)) else [raw]
    out: dict[str, dict] = {}
    for r in rows:
        row = channel_row(r)
        if row:
            out[row["platform"]] = row
    return list(out.values())


def same_channel(a: dict, b: dict) -> bool:
    """Do these two channel rows name the SAME account? Platform plus either identity, `@` and case aside."""
    if norm(a.get("platform")) != norm(b.get("platform")):
        return False
    for k in ("chatId", "handle"):
        for j in ("chatId", "handle"):
            x, y = norm(str(a.get(k) or "")).lstrip("@"), norm(str(b.get(j) or "")).lstrip("@")
            if x and x == y:
                return True
    return False


def owner_of_channel(contacts: list[dict], rows: list[dict]) -> dict | None:
    """The contact who ALREADY holds one of these accounts, if any (V2-693).

    An account is a stronger identity than a name: «Cryptonite» and «Pruebas Zaelar» are two names for one
    Telegram user, and `add_contact` deduped on name+city alone — so the second name made a second row. The
    operator found it himself: «¿cómo vamos a tener dos contactos que tienen el mismo nickname de Telegram?».
    Two owners is not a merge, it is an ambiguity, and this answers None so the caller writes nothing."""
    hits = [c for c in contacts
            if any(same_channel(ch, row) for ch in c.get("channels") or [] for row in rows)]
    return hits[0] if len(hits) == 1 else None


def merge_channel(c: dict, row: dict) -> None:
    """Set one channel on a contact, keeping what the new row does not say (an operator fixing a handle must
    not erase the chatId the traffic already taught us, and vice versa)."""
    chs = c.setdefault("channels", [])
    old = next((ch for ch in chs if ch.get("platform") == row["platform"]), None)
    if old is None:
        chs.append(row)
        return
    for k in ("handle", "chatId"):
        if row.get(k):
            old[k] = row[k]
    old["source"] = row.get("source") or old.get("source") or "operator"
    if row.get("volume"):
        old["volume"] = row["volume"]
    if row.get("last_seen"):
        old["last_seen"] = row["last_seen"]
