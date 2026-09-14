"""widgets/directory.py — WHO a name is, and HOW to reach that person (V2-683).

The layer module every outbound door asks before writing to somebody. It sits beside `brief.py` and
`refs.py` for the same reason they do: the knowledge is about the CATALOG of widgets, not about one of
them, and a widget that needed it would otherwise have to import another widget.

Three questions, and each one has exactly one honest answer here:

  · `resolve(name)`   — WHO did he mean? Returns the matching contacts, never a guess. Zero or several is
                        an answer, not a failure: the caller ASKS (the `refs.py` doctrine — a wrong
                        recipient is the one mistake an outbound door can make that cannot be undone).
  · `channel_for(c)`  — by WHICH channel? The preferred one if he fixed it, else the one he actually uses
                        (volume), else the only one there is. Ambiguity with no preference answers None.
  · `note_inbound()`  — passive learning (V2-052's closed decision 3): every message that arrives already
                        carries an identity for its platform, so the contacts he really talks to build
                        their own channel list. It NEVER creates a contact and never writes on an
                        ambiguous match: a directory that fills itself with strangers is worse than one
                        that stays empty.

## What a channel is

    {"platform": "telegram", "handle": "@ivanm", "chatId": "123456",
     "source": "operator|observed|field", "last_seen": 1757700000.0, "volume": 14}

`handle` is what the connector needs to OPEN a conversation (a username, a phone, an address); `chatId` is
what identifies it once it exists. A channel may carry either or both — Telegram can start from a handle
and learns its chatId on the first exchange; email's address is both at once.

## The one asymmetry, written down on purpose

A stored `email` field IS an email channel: the address is the whole capability, so it is derived. A stored
`phone` is NOT a WhatsApp channel — having somebody's number is not proof they use WhatsApp, and deriving
one would let «mándale un WhatsApp» reach a number that never agreed to be reachable there. So a phone is
offered only when the caller NAMES whatsapp explicitly (he asked for that channel, and a number that has no
WhatsApp fails loudly at the bridge, which is an honest answer) and never as the automatic choice.
"""
from __future__ import annotations

import re
import time
import unicodedata

from loguru import logger

#: Platforms that can carry an outbound message today. Kept here (not imported from `connectors.messaging`)
#: because the widget layer must not depend on a connector being installed to answer «who is this».
PLATFORMS = ("whatsapp", "telegram", "email")

#: Minimum digits two phone numbers must share, as a suffix, to be the same number. Country prefixes vary in
#: length and a stored number may or may not carry one, so a suffix comparison is the only general rule; the
#: floor keeps «600» from matching half the directory.
_PHONE_MIN_DIGITS = 7


def _norm(s) -> str:
    """Accent/case-insensitive comparable form — the same normalisation the contacts store itself uses."""
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def _digits(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _same_phone(a, b) -> bool:
    da, db = _digits(a), _digits(b)
    if len(da) < _PHONE_MIN_DIGITS or len(db) < _PHONE_MIN_DIGITS:
        return False
    return da.endswith(db) or db.endswith(da)


def _contacts() -> list[dict]:
    try:
        from .contactos import data as _cd
        return list(_cd.load_db().get("contacts", []))
    except Exception:
        return []


# ── reading ────────────────────────────────────────────────────────────────────────────────────────────
def channels(contact: dict) -> list[dict]:
    """Every channel this contact has, stored ones first and the derived email last (see the module note)."""
    out = [dict(ch) for ch in (contact.get("channels") or []) if str(ch.get("platform") or "").strip()]
    have = {str(ch.get("platform")) for ch in out}
    addr = str(contact.get("email") or "").strip()
    if addr and "@" in addr and "email" not in have:
        out.append({"platform": "email", "handle": addr, "chatId": addr, "source": "field",
                    "last_seen": 0.0, "volume": 0})
    return out


def channel_for(contact: dict, platform: str = "") -> dict | None:
    """The channel to write to. With `platform` named, THAT one or nothing. Without it: the preferred one,
    then the most used, then the only one — and None when there is nothing to choose from or the choice is
    a coin toss, because guessing a channel is how a private message lands in the wrong app."""
    if not isinstance(contact, dict):
        return None
    chs = channels(contact)
    want = _norm(platform)
    if want:
        hit = next((c for c in chs if _norm(c.get("platform")) == want), None)
        if hit:
            return hit
        # He NAMED whatsapp and we hold a phone: try it (see the module's asymmetry note). Never the reverse.
        if want == "whatsapp":
            tel = str(contact.get("phone") or "").strip()
            if _digits(tel):
                return {"platform": "whatsapp", "handle": tel, "chatId": "", "source": "field",
                        "last_seen": 0.0, "volume": 0}
        return None
    pref = _norm(contact.get("preferred"))
    if pref:
        hit = next((c for c in chs if _norm(c.get("platform")) == pref), None)
        if hit:
            return hit
    if not chs:
        return None
    if len(chs) == 1:
        return chs[0]
    used = [c for c in chs if float(c.get("volume") or 0) > 0]
    if used:
        used.sort(key=lambda c: (-float(c.get("volume") or 0), -float(c.get("last_seen") or 0)))
        # A tie between two channels he uses equally is a real ambiguity: ask rather than flip a coin.
        if len(used) == 1 or float(used[0].get("volume") or 0) > float(used[1].get("volume") or 0):
            return used[0]
    return None


def resolve(name: str) -> list[dict]:
    """The contacts `name` can mean. Exact name wins outright; otherwise every contact whose name contains
    all the words said. An empty name resolves to NOBODY — «mándale un mensaje» with no name must ask, and
    returning the whole directory would let a caller pick the first row."""
    q = _norm(name)
    if not q:
        return []
    people = _contacts()
    exact = [c for c in people if _norm(c.get("name")) == q]
    if exact:
        return exact
    words = [w for w in q.split(" ") if w]
    out = []
    for c in people:
        hay = _norm(c.get("name"))
        if hay and all(w in hay for w in words):
            out.append(c)
    if out:
        return out
    # An address or a number said out loud instead of a name.
    for c in people:
        if "@" in q and _norm(c.get("email")) == q:
            out.append(c)
        elif _same_phone(q, c.get("phone")):
            out.append(c)
    if out:
        return out
    # Last resort: the name as the operator SPELLS it, a letter off the name as it is filed (V2-698).
    # Measured 2026-09-15: he dictates «Kryptonite», the row says «Cryptonite», and `send_to` refused with
    # «no tengo a Kryptonite en el directorio» while the worker guessed its way to the right spelling. Same
    # rule as the playlist garble (V2-650b): a UNIQUE near match resolves, two near matches stay a refusal —
    # writing to the wrong person is the failure this must never trade for.
    import difflib
    scored = sorted(((difflib.SequenceMatcher(None, q, _norm(c.get("name"))).ratio(), c) for c in people
                     if _norm(c.get("name"))), key=lambda t: -t[0])
    if scored and scored[0][0] >= 0.8 and (len(scored) == 1 or scored[1][0] < 0.7):
        return [scored[0][1]]
    return out


def find_by_channel(platform: str, chat_id) -> dict | None:
    """The contact a live conversation belongs to, or None. Used to name a thread's other side."""
    p, cid = _norm(platform), str(chat_id or "").strip()
    if not p or not cid:
        return None
    for c in _contacts():
        for ch in c.get("channels") or []:
            if _norm(ch.get("platform")) == p and str(ch.get("chatId") or "") == cid:
                return c
    return None


# ── passive learning ───────────────────────────────────────────────────────────────────────────────────
def _match_sender(people: list[dict], platform: str, msg: dict) -> list[dict]:
    """Which contacts this inbound message could be from. Identity first (a handle or address we already
    hold is proof), name last (two friends called «Javi» is exactly the case that must NOT write)."""
    p = _norm(platform)
    chat_id = str(msg.get("chatId") or "").strip()
    sender = str(msg.get("senderId") or "").strip()
    name = str(msg.get("from") or msg.get("senderName") or "").strip()

    by_id = [c for c in people
             if any(_norm(ch.get("platform")) == p
                    and (str(ch.get("chatId") or "") == chat_id and chat_id
                         or (_norm(ch.get("handle")) == _norm(sender) and sender))
                    for ch in c.get("channels") or [])]
    if by_id:
        return by_id
    if p == "email" and "@" in sender:
        hit = [c for c in people if _norm(c.get("email")) == _norm(sender)]
        if hit:
            return hit
    if p in ("whatsapp", "telegram") and _digits(sender or chat_id):
        hit = [c for c in people if _same_phone(sender or chat_id, c.get("phone"))]
        if hit:
            return hit
    if name:
        return [c for c in people if _norm(c.get("name")) == _norm(name)]
    return []


def note_inbound(platform: str, msg: dict) -> bool:
    """One inbound message teaches the directory. Returns True when something was written.

    Deliberately narrow, and every one of these is a case that WOULD have written something wrong:
      · a GROUP teaches nothing (the sender is not the conversation's identity);
      · no match creates no contact (his directory is his, not a log of everyone who wrote);
      · two matches write NOTHING (the ambiguity is the finding — a wrong handle on the wrong contact
        would then be used, silently, the next time he says «escríbele»).
    """
    try:
        if not isinstance(msg, dict) or msg.get("isGroup"):
            return False
        p = _norm(platform)
        if p not in PLATFORMS:
            return False
        from .contactos import data as _cd
        db = _cd.load_db()
        people = db.get("contacts") or []
        hits = _match_sender(people, p, msg)
        if len(hits) != 1:
            return False
        c = hits[0]
        chat_id = str(msg.get("chatId") or "").strip()
        sender = str(msg.get("senderId") or "").strip()
        handle = sender or chat_id
        chs = c.setdefault("channels", [])
        row = next((ch for ch in chs if _norm(ch.get("platform")) == p), None)
        if row is None:
            row = {"platform": p, "handle": handle, "chatId": chat_id,
                   "source": "observed", "volume": 0}
            chs.append(row)
        # The chatId ALWAYS follows the traffic: it is MACHINE identity, and holding a stale one would send
        # into a conversation that no longer exists. The HANDLE does not — it is what the operator typed
        # («@ivanm»), and a sender id the transport renders differently must never replace it. (Written this
        # way after a disarm came back GREEN: the guard that named `source` protected nothing, because this
        # emptiness check was already doing the work — V2-655's «a guard that guards nothing».)
        if chat_id:
            row["chatId"] = chat_id
        if handle and not str(row.get("handle") or "").strip():
            row["handle"] = handle
        row["volume"] = int(row.get("volume") or 0) + 1
        row["last_seen"] = float(msg.get("ts") or time.time())
        _cd.store.save(_cd.WIDGET_ID, db)
        return True
    except Exception:
        return False


def note_reached(platform: str, chat_id, contact_id: str) -> bool:
    """A message we SENT resolved this contact to a real conversation id — learn it (V2-693).

    ⚠️ Until today this was discovered and thrown away, and it is how the directory grew a twin. The
    operator asks by name, `resolve_target` hands the connector a HANDLE («@cryptonite_fund»), the connector
    asks the platform who that is and gets back a numeric chat id — the only place that id exists. Nobody
    wrote it down. So when the same person answered, `_match_sender` had a numeric id on one side and an
    `@handle` on the other, matched nothing, and the reply arrived as a stranger; a later `add_contact`
    then created a SECOND row for one person with one Telegram account. His words: «¿cómo vamos a tener dos
    contactos que tienen el mismo nickname de Telegram?».

    Same rule as `note_inbound`: the chatId follows the traffic, the operator's own handle is never
    overwritten. Never raises — a directory that cannot learn must not break a send that already happened.
    """
    try:
        cid = str(chat_id or "").strip()
        p = _norm(platform)
        if not cid or not contact_id or p not in PLATFORMS:
            return False
        from .contactos import data as _cd
        db = _cd.load_db()
        c = next((x for x in db.get("contacts") or [] if str(x.get("id") or "") == str(contact_id)), None)
        if c is None:
            return False
        chs = c.setdefault("channels", [])
        row = next((ch for ch in chs if _norm(ch.get("platform")) == p), None)
        if row is None:
            row = {"platform": p, "handle": cid, "chatId": cid, "source": "observed", "volume": 0}
            chs.append(row)
        elif str(row.get("chatId") or "") == cid:
            return False                      # already known — no write, no churn on every single send
        else:
            row["chatId"] = cid
        _cd.store.save(_cd.WIDGET_ID, db)
        logger.info(f"directory: {c.get('name')} → {p}:{cid}")
        return True
    except Exception:
        return False


def note_many(platform: str, msgs) -> int:
    """`note_inbound` over a batch — the shape the messaging store fans out. Never raises."""
    n = 0
    for m in msgs or []:
        try:
            if note_inbound(platform, m):
                n += 1
        except Exception:
            continue
    return n
