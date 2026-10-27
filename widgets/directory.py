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


def _phones(contact: dict) -> list[str]:
    """EVERY number this contact holds, not just the primary (V2-715). A company keeps its switchboard, its
    mobile and its billing line; a resolver that only ever read `phone` would fail to recognise the very
    number the operator dictated, on a row that holds it."""
    out = [str(r.get("value") or "") for r in (contact.get("phones") or []) if isinstance(r, dict)]
    head = str(contact.get("phone") or "").strip()
    return out or ([head] if head else [])


def _emails(contact: dict) -> list[str]:
    out = [str(r.get("value") or "") for r in (contact.get("emails") or []) if isinstance(r, dict)]
    head = str(contact.get("email") or "").strip()
    return out or ([head] if head else [])


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
            tel = next((t for t in _phones(contact) if _digits(t)), "")
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


def reachable(question: str) -> str:
    """The people a free-text question names, with how each one is reached — for a card that WRITES to people.

    Demo pass 2026-09-28, C5: asked «is there a contact called Rowan? does he have Telegram?», the messaging card
    could only see its inbox and said no, while its own `send_to` resolves through this module. A card that sends
    answers recipient questions from here; this layer asks the directory's own lookup, so no widget imports
    another. "" when nobody is named."""
    try:
        from .contactos.lookup import read_query as _lookup
        return str(_lookup(question) or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def resolve(name: str, *, tolerant: bool = True) -> list[dict]:
    """The contacts `name` can mean. Exact name wins outright; otherwise every contact whose name contains
    all the words said. An empty name resolves to NOBODY — «mándale un mensaje» with no name must ask, and
    returning the whole directory would let a caller pick the first row. `tolerant=False` stops before the
    spelling-tolerant last resort: a door that LEAVES asks about a near name (`near`) instead of using it."""
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
        if "@" in q and any(_norm(a) == q for a in _emails(c)):
            out.append(c)
        elif any(_same_phone(q, tel) for tel in _phones(c)):
            out.append(c)
    if out or not tolerant:
        return out
    # TOLERANT last resort, through the ONE shared matcher (`widgets/textmatch`, V2-705). The operator, 2026-09-15:
    # «una C por una K, una letra que falta, una H… que sea flexible, preciso, pero inteligente», and «tiene que
    # funcionar para cualquiera» — so contacts, calendar and messages all fall to the same primitive. Measured:
    # he dictates «Kryptonite», the row says «Cryptonite». Every near match ABOVE the floor is returned, not just
    # a unique one: two matches are an AMBIGUITY the caller asks about (the send door does), never a silent pick —
    # writing to the wrong person is the one thing this must not trade for, and «pregúntale cuál» is the human move.
    from . import textmatch
    near = [c for _score, c in textmatch.rank(name, people, key=lambda c: c.get("name"), floor=0.8)]
    return near or out


def near(name: str) -> list[dict]:
    """The contacts only the spelling-tolerant match finds for `name` — what a door that leaves names back to him as
    «¿te refieres a X?» (the operator, 2026-10-15: who a message goes to is never left in doubt)."""
    return [] if resolve(name, tolerant=False) else resolve(name)


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
        hit = [c for c in people if any(_norm(a) == _norm(sender) for a in _emails(c))]
        if hit:
            return hit
    if p in ("whatsapp", "telegram") and _digits(sender or chat_id):
        hit = [c for c in people if any(_same_phone(sender or chat_id, tel) for tel in _phones(c))]
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
    operator asks by name, `resolve_target` hands the connector a HANDLE («@northfund_demo»), the connector
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


# ── naming a conversation (V2-819) ─────────────────────────────────────────────────────────────────────
#: The WhatsApp address suffixes whose digits ARE a phone number. A `@lid` (linked identity) and a `@g.us`
#: (group) carry digits that are not a phone, and reading them as one could put a contact's name on a stranger.
_PHONE_JID = ("@s.whatsapp.net", "@c.us")


def _phone_of(platform: str, chat_id) -> str:
    """The phone number a conversation's id carries, or "". Only where the id IS a number: a WhatsApp phone
    JID or a bare «+34 600…». A Telegram id is an account number, never a phone."""
    cid = str(chat_id or "").strip()
    if not cid:
        return ""
    if "@" in cid:
        return _digits(cid.split("@", 1)[0]) if _norm(platform) == "whatsapp" and cid.endswith(_PHONE_JID) else ""
    if _norm(platform) == "telegram" and not cid.startswith("+"):
        return ""
    return _digits(cid) if re.fullmatch(r"\+?[\d\s().-]{7,}", cid) else ""


def _photo(contact: dict) -> str:
    """A picture the card can draw without a fetch of its own: same-origin or inline. A remote URL is left out
    rather than handed to a widget that must never reach the network (widgets/validator.py)."""
    a = str((contact or {}).get("avatar") or "").strip()
    return a if a.startswith(("/widgets/", "data:image/")) else ""


def namer(people: list[dict] | None = None):
    """ONE resolver for the name and picture of the other side of a conversation, for every list and header
    that shows one. Contacts are read ONCE per call to `namer()` — a view names dozens of rows.

        name = namer()
        name("whatsapp", "34600111222@s.whatsapp.net", fallback="Mamá ❤")  ->  {"name": "mama", "photo": ""}

    Order, each step only when the previous one has nothing:
      1. the contact that already holds this conversation (a channel learned or set on it);
      2. the contact whose phone (or address, for mail) is the one this conversation's id carries;
      3. the platform's own display name (`fallback`: pushname, Telegram name, a mail's display name);
      4. the bare id, without its transport suffix.
    A contact match must be UNIQUE: two rows holding the same number is an ambiguity, and the platform's own
    name is then more honest than either of them."""
    if people is None:
        try:
            from .contactos import data as _cd
            people = _cd.visible(_cd.load_db())
        except Exception:  # noqa: BLE001
            people = []
    people = [c for c in people if isinstance(c, dict) and c.get("kind") != "group" and str(c.get("name") or "").strip()]

    def _one(hits: list[dict]) -> dict | None:
        uniq = {id(c): c for c in hits}
        return next(iter(uniq.values())) if len(uniq) == 1 else None

    def resolve(platform: str, chat_id, fallback: str = "") -> dict:
        p, cid = _norm(platform), str(chat_id or "").strip()
        hit = None
        if p and cid:
            hit = _one([c for c in people for ch in c.get("channels") or []
                        if _norm(ch.get("platform")) == p and str(ch.get("chatId") or "") == cid])
            if hit is None and p == "email" and "@" in cid:
                hit = _one([c for c in people if any(_norm(a) == _norm(cid) for a in _emails(c))])
            if hit is None:
                tel = _phone_of(p, cid)
                if tel:
                    hit = _one([c for c in people if any(_same_phone(tel, t) for t in _phones(c))])
        if hit is not None:
            return {"name": str(hit.get("name")).strip(), "photo": _photo(hit), "contactId": str(hit.get("id") or "")}
        name = str(fallback or "").strip() or cid.split("@", 1)[0]
        return {"name": name, "photo": "", "contactId": ""}

    return resolve
