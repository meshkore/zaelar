"""widgets/directory.py — WHO a name is, and HOW to reach that person (V2-683).

The layer module every outbound door asks before writing to somebody; beside `brief.py` and `refs.py` because
the knowledge is about the CATALOG of widgets, not one of them.

Three questions, and each one has exactly one honest answer here:

  · `resolve(name)`   — WHO did he mean? The matching contacts, never a guess; zero or several and the caller
                        ASKS (a wrong recipient is the one outbound mistake that cannot be undone).
  · `channel_for(c)`  — by WHICH channel? The preferred one if he fixed it, else the one he actually uses
                        (volume), else the only one there is. Ambiguity with no preference answers None.
  · `note_inbound()`  — passive learning (V2-052): an arriving message carries its platform identity, so the
                        contacts he talks to build their channel list. It NEVER creates a contact and never
                        writes on an ambiguous match.

## What a channel is

    {"platform": "telegram", "handle": "@ivanm", "chatId": "123456",
     "source": "operator|observed|field", "last_seen": 1757700000.0, "volume": 14}

`handle` OPENS a conversation (username, phone, address); `chatId` identifies it once it exists — either or both.

## The one asymmetry, written down on purpose

A stored `email` field IS an email channel: the address is the whole capability, so it is derived. A stored
`phone` is NOT a WhatsApp channel (a number is no proof they use WhatsApp): a phone is offered only when the
caller NAMES whatsapp explicitly, never as the automatic choice.
"""
from __future__ import annotations

import functools
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


# ── how close a person is (V2-849) ─────────────────────────────────────────────────────────────────────────
#: Levels, closest first. CIRCLE: he gave a word about this person (a favorite, an alias, a relation). ACTIVE: there
#: was traffic either way, on any channel, within the window. BACKGROUND: everything else — kept, never deleted,
#: consulted only when nothing closer matches. 0: never a candidate (hidden, blocked). Computed, never stored: a
#: person moves on their own when the conversation starts or stops.
CIRCLE, ACTIVE, BACKGROUND = 3, 2, 1
#: How many people one «which one?» names — the send door's question reads this one number.
CANDIDATES_MAX = 3


_WINDOW: dict = {}


def active_days() -> float:
    """The activity window, from genesis `contacts.active_days` with the install's `config/contacts.json` on top. Read
    at most once every few seconds: it rides every name lookup of every turn, over thousands of contacts."""
    if _WINDOW and time.time() - _WINDOW["at"] < 5.0:
        return _WINDOW["days"]
    _WINDOW.update({"days": _read_window(), "at": time.time()})
    return _WINDOW["days"]


def _read_window() -> float:
    import json
    from pathlib import Path
    days = 90.0
    try:
        g = json.loads((Path(__file__).resolve().parents[1] / "nucleo" / "genesis.json").read_text(encoding="utf-8"))
        days = float((g.get("contacts") or {}).get("active_days") or days)
        from nucleo import workspace as _ws
        over = _ws.root() / "config" / "contacts.json"
        if over.exists():
            days = float((json.loads(over.read_text(encoding="utf-8")) or {}).get("active_days") or days)
    except Exception as e:  # noqa: BLE001 — unreadable: the default window
        logger.debug(f"directory: activity window unreadable ({e!r}) — {days:g} days")
    return days


def _last_seen(c: dict) -> float:
    return max([float(ch.get("last_seen") or 0) for ch in c.get("channels") or [] if isinstance(ch, dict)] or [0.0])


def level(c: dict, *, since: float | None = None) -> int:
    """How close this contact is — one of the levels above, or 0 when it is never a candidate."""
    if not isinstance(c, dict) or c.get("hidden"):
        return 0
    flags = set(c.get("flags") or [])
    if "blocked" in flags:
        return 0
    if "closed" in flags:
        return BACKGROUND
    if c.get("favorite") or c.get("aliases") or c.get("relation"):
        return CIRCLE
    since = time.time() - active_days() * 86400 if since is None else since
    return ACTIVE if _last_seen(c) >= since else BACKGROUND


def closest_first(people: list[dict]) -> list[dict]:
    """These people, closest level first and the most recently talked-to first within a level; never-candidates out."""
    since = time.time() - active_days() * 86400
    ranked = [(level(c, since=since), _last_seen(c), c) for c in people]
    return [c for lv, _t, c in sorted((r for r in ranked if r[0]), key=lambda r: (-r[0], -r[1]))]


def _closest(hits: list[dict]) -> list[dict]:
    """A match's answer: the ONE person of his circle when exactly one matches there (his word made them his), else
    every match, closest first — several is a question, and the question names the closest ones."""
    ordered = closest_first(hits)
    circle = [c for c in ordered if level(c) == CIRCLE]
    return circle if len(circle) == 1 else ordered


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


def names(c: dict) -> list[str]:
    """Every name a person is known by: his own, and the one each of his chats shows (V2-850 — the WhatsApp chat
    «Pablo Sabin» linked by phone to the «Pablo FF» of his address book is found by either)."""
    out = [str(c.get("name") or "")]
    for ch in c.get("channels") or []:
        n = str((ch or {}).get("name") or "").strip()
        if n and _norm(n) not in {_norm(x) for x in out}:
            out.append(n)
    return [n for n in out if n.strip()]


# ── one ranking (V2-854) ─────────────────────────────────────────────────────────────────────────────────────
#: How strongly a name matches a contact, strongest first. ALIAS: a word HE gave this person. EXACT: the whole name,
#: or the number or address said. WORDS: every word said is a word of the name. PART: a word said sits inside a
#: word of a compound name («salvador» in «salvadoresteban»). SOUND: a word said SOUNDS like a word of the name
#: (`sound`). NEAR: a spelling-tolerant last resort, only when nothing else matched.
#: The values are POINTS (`_points`): a whole name outweighs a step of closeness, so «Ana» is the contact named Ana
#: before «Ana Mora» of the same standing; every word, a part or a sound weigh less than a favorite does.
ALIAS, EXACT, WORDS, PART, SOUND, NEAR = 9, 8, 5, 4, 2, 1
#: The quotes that make a name literal: «"Raquel"» is that spelling and no other.
_QUOTES = "\"'«»“”‘’„"


@functools.lru_cache(maxsize=65536)
def _tokens_of(s: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[^\W_]+", _norm(s)))


def _tokens(s) -> list[str]:
    return list(_tokens_of(str(s or "")))


@functools.lru_cache(maxsize=65536)
def sound(word: str) -> str:
    """How a word SOUNDS, for any language written in Latin letters — a normaliser, never a table of names: accents
    off, then the spellings that write one sound twice fold into one (qu/k/hard c, soft c/z/s, soft g/j, b/v, ph/f,
    ll/y, ch/sh, a silent h, a y used as a vowel, doubled letters). «Raquel» and «Rakel», «Jordi» and «Jordy»,
    «Vanessa» and «Banesa», «Karó» and «Caro» sound the same."""
    w = re.sub(r"[^a-z0-9]", "", _norm(word))
    for a, b in (("ph", "f"), ("qu", "k"), ("ck", "k"), ("ch", "x"), ("sh", "x"), ("ll", "y")):
        w = w.replace(a, b)
    w = re.sub(r"c(?=[eiy])", "s", w).replace("c", "k").replace("q", "k")
    w = re.sub(r"g(?=[eiy])", "j", w).replace("z", "s").replace("v", "b").replace("h", "")
    w = re.sub(r"y(?![aeiou])", "i", w)
    return re.sub(r"(.)\1+", r"\1", w)


def _word(w: str, toks, literal: bool) -> int:
    best = 0
    for t in toks:
        if w == t:
            return WORDS
        if literal:
            continue
        if len(w) >= 3 and w in t:
            best = max(best, PART)
        elif len(sound(w)) >= 3 and sound(w) == sound(t):
            best = max(best, SOUND)
    return best


def strength(q: str, c: dict, *, words: list[str] | None = None, literal: bool = False) -> int:
    """The strongest reason `q` (already `_norm`ed) names this contact — one of the strengths above, 0 for none."""
    words = _tokens(q) if words is None else words
    said = [sound(w) for w in words]
    for a in c.get("aliases") or []:
        if _norm(a) == q or (not literal and said and [sound(t) for t in _tokens(a)] == said):
            return ALIAS
    best = 0
    for n in names(c):
        toks = _tokens_of(n)
        if " ".join(toks) == q or _norm(n) == q:
            return EXACT
        if words and toks:
            best = max(best, min(_word(w, toks, literal) for w in words))
    if "@" in q and any(_norm(a) == q for a in _emails(c)):
        return EXACT
    if any(_same_phone(q, tel) for tel in _phones(c)):
        return EXACT
    return best


def closeness(c: dict, nats: list[dict] | None = None) -> int:
    """Where he keeps this person, on the scale the manifest declares (`native_groups`, closest first): 1 + how
    high the first native this contact belongs to ranks (a relation counts for the native that declares it), 1 for
    any other contact, 0 for one with no way to reach (`unclassified`; the act filter keeps them out of a send)."""
    from .contactos import groups as _groups, model as _model
    if "closed" in set(c.get("flags") or []):
        return 1
    rank = _groups.native_rank(c, nats)
    return 1 + rank if rank else (0 if _model.unclassified(c) else 1)


def _points(s: int, c: dict, since: float, nats) -> int:
    """One number to rank by: a step of closeness weighs two of strength, and a recent conversation is a FLAG worth
    more than the whole declared scale — the operator (2026-11-05): the people he has talked to lately are the first
    level, even outside the relation scale. A recent namesake outranks a favorite he has not talked to; a favorite
    he talks to stays on top. Derived from the scale's own size, so a native declared later keeps it so."""
    recent = 2 * (len(nats or ()) + 2) if _last_seen(c) >= since else 0
    return 2 * closeness(c, nats) + recent + s


def _reaches(c: dict, platform: str) -> bool:
    """Can the act reach this person? "" = by any channel; a platform = by that one (`channel_for`)."""
    from .contactos import model as _model
    p = _norm(platform)
    return channel_for(c, p) is not None if p else not _model.unclassified(c)


_MARGIN: dict = {}


def clear_margin() -> float:
    """How far ahead the best match must be to be used without asking — the rule `widget:contactos` · `clear_margin`
    (the manifest's default, his row on top). Read at most every few seconds: it rides every name lookup."""
    if _MARGIN and time.time() - _MARGIN["at"] < 5.0:
        return _MARGIN["v"]
    v = 3.0
    try:
        import rules
        v = float(rules.value(rules.path(widget="contactos"), "clear_margin", v))
    except Exception as e:  # noqa: BLE001 — unreadable: the default margin
        logger.debug(f"directory: clear_margin unreadable ({e!r}) — {v:g}")
    _MARGIN.update({"v": v, "at": time.time()})
    return v


def resolve(name: str, *, tolerant: bool = True, platform: str | None = None) -> list[dict]:
    """The contacts `name` can mean — ONE ranking (V2-854), never a ladder that stops at its first rung.

    Every contact gets the strongest reason it matches (`strength`: his word for the person · the exact name or
    number · every word · a word inside a compound name · the same SOUND, any language · and, only when nothing
    else matched and `tolerant`, a near spelling) and how close he is (`closeness`: a recent conversation, then the
    native scale the manifest declares — favorites, family, friends, colleagues — then the rest, and last the
    unclassified, who have no way to be reached). A word of his (`aliases`) names its person outright: one person
    per word (`set_alias`). Otherwise the best is the answer ALONE when it leads the next by the declared margin
    (`clear_margin`, a rule with readers); else every match, best first — several is a question, and the
    question names the first `CANDIDATES_MAX`.

    `platform` is the ACT, and it filters first: a WhatsApp/Telegram send keeps who is reachable there, a mail who
    has an address, "" any send (the unclassified are out). When the act leaves nobody, the people the name
    matches come back as they rank, so the door can say what is missing («no tengo su correo»), never «no one».
    A name in quotes is matched literally (no sound, no compound, no near spelling). An empty name is NOBODY —
    returning the directory would let a caller pick the first row."""
    raw = str(name or "").strip()
    literal = len(raw) >= 2 and raw[0] in _QUOTES and raw[-1] in _QUOTES
    q = _norm(raw[1:-1] if literal else raw)
    if not q:
        return []
    people = [c for c in _contacts() if level(c)]
    from .contactos import groups as _groups
    nats = _groups.declared()
    since = time.time() - active_days() * 86400
    words = _tokens(q)
    scored = []
    for c in people:
        s = strength(q, c, words=words, literal=literal)
        if s:
            scored.append((s, c))
    if not scored and tolerant and not literal:
        from . import textmatch      # the ONE shared spelling-tolerant matcher (V2-705): «Kryptonite» → «Cryptonite»
        scored = [(NEAR, c) for _score, c in textmatch.rank(raw, people, key=lambda c: c.get("name"), floor=0.8)]
    if platform is not None:
        able = [(s, c) for s, c in scored if _reaches(c, platform)]
        scored = able or scored
    if not scored:
        return []
    mine = [c for s, c in scored if s == ALIAS]
    if len(mine) == 1:
        return mine
    ranked = sorted(((_points(s, c, since, nats), _last_seen(c), c) for s, c in scored), key=lambda r: (-r[0], -r[1]))
    if len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= clear_margin():
        return [ranked[0][2]]
    return [c for _p, _t, c in ranked]


def by_relation(relation: str) -> list[dict]:
    """The people he said ARE this to him (`relation`, a value of the contacts manifest's `relations`), closest first.
    A relation is never read off a name: «Amiga Mama» is a label, not his mother."""
    rel = _norm(relation)
    return [c for c in closest_first(_contacts()) if rel and _norm(c.get("relation")) == rel] if rel else []


# ── his answer to «which one?» becomes his word (V2-849 D1) ──────────────────────────────────────────────────
#: How long the question a send door asked waits for his answer: the next turn or two, never a session.
ASKED_FOR_S = 300.0
_ASKED: dict = {}


def asked(spoken: str, candidates: list[dict], relation: str = "") -> None:
    """A door could not tell who `spoken` is and asked him. A narrower question about the SAME word (his answer
    matched several again — «Raquel Salvador», two rows) keeps the word he first used: that is what he will say."""
    ids = [str(c.get("id") or "") for c in candidates or [] if c.get("id")]
    live = _ASKED and time.time() - float(_ASKED.get("at") or 0) <= ASKED_FOR_S
    if live and ids and set(ids) <= set(_ASKED.get("ids") or ids):
        _ASKED.update({"ids": ids, "at": time.time()})
        return
    _ASKED.clear()
    _ASKED.update({"spoken": str(spoken or "").strip(), "ids": ids, "relation": _norm(relation), "at": time.time()})


def answered(contact: dict) -> dict:
    """When `contact` is his answer to the question just asked, the word he used becomes its alias — and the relation,
    when he named the person by one. Returns what was learned ({} when nothing was asked, the answer is not one of
    the people asked about, or the word IS the name). Written through the contacts card's own actions."""
    q = dict(_ASKED)
    if not q or time.time() - float(q.get("at") or 0) > ASKED_FOR_S or not isinstance(contact, dict):
        return {}
    cid = str(contact.get("id") or "")
    if q.get("ids") and cid not in q["ids"]:
        return {}
    _ASKED.clear()
    spoken = str(q.get("spoken") or "").strip()
    try:
        from .contactos import data as _cd
        learned: dict = {}
        if q.get("relation"):
            learned["relation"] = q["relation"]
        if spoken and _norm(spoken) != _norm(contact.get("name")):
            learned["alias"] = spoken
        if learned:
            # V2-854 — a word learned from his pick, marked so (`aliasSources`); he can still set or remove it by hand.
            _cd.apply_action("set_alias", {"contactId": cid, **learned, "source": "learned"})
        if learned:
            learned["contact"] = str(contact.get("name") or "")
            logger.info(f"directory: his answer — {learned}")
        return learned
    except Exception as e:  # noqa: BLE001 — a lesson not written never breaks the send it rode on
        logger.warning(f"directory: could not keep his answer ({e!r})")
        return {}


def answered_id(contact_id) -> dict:
    """`answered` for the contact with this id ({} for none)."""
    cid = str(contact_id or "")
    c = next((x for x in _contacts() if cid and str(x.get("id") or "") == cid), None)
    return answered(c) if c else {}


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
    # V2-849 — only an id that IS a number is a phone (`_phone_of`): a WhatsApp `@lid` and a Telegram account id
    # carry digits that are not one, and reading them as one linked a stranger to whoever shared the suffix.
    tel = _phone_of(p, sender) or _phone_of(p, chat_id)
    if p in ("whatsapp", "telegram") and tel:
        hit = [c for c in people if any(_same_phone(tel, t) for t in _phones(c))]
        if hit:
            return hit
    if name:
        return [c for c in people if _norm(c.get("name")) == _norm(name)]
    return []


def _linked_by_name(platform: str, msg: dict, c: dict) -> bool:
    """Did the sender reach this contact only by NAME (no id, address or number of ours)? A display name is the
    weakest proof there is — the link is kept, and marked, so certainty can read it (V2-849)."""
    p = _norm(platform)
    ids = {str(msg.get("chatId") or ""), str(msg.get("senderId") or "")} - {""}
    if any(_norm(ch.get("platform")) == p and ({str(ch.get("chatId") or ""), str(ch.get("handle") or "")} & ids)
           for ch in c.get("channels") or []):
        return False
    tel = _phone_of(p, msg.get("senderId")) or _phone_of(p, msg.get("chatId"))
    return not (tel and any(_same_phone(tel, t) for t in _phones(c)))


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
            if _linked_by_name(p, msg, c):
                row["linked_by"] = "name"
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


def note_reached(platform: str, chat_id, contact_id: str = "", ts=None) -> bool:
    """A message that LEFT toward a conversation — the operator's own, from here or from his phone — teaches the
    directory two things (V2-693, V2-849):

      · with `contact_id` (a send that resolved a person), the real conversation id: the connector learns the numeric
        chat id from a HANDLE, and nobody wrote it down — the reply then matched nothing, arrived as a stranger, and a
        later `add_contact` made a twin row for one Telegram account;
      · the TRAFFIC, in his direction: `volume` and `last_seen` grow on what he writes too, so a person he writes to
        every week and who never answers is as close as one who writes to him. Without it, closeness and the default
        channel only counted what came in.

    Same rule as `note_inbound`: the chatId follows the traffic, the operator's own handle is never overwritten, and
    without `contact_id` only the contact that ALREADY holds this conversation is touched (never a guess). Never
    raises — a directory that cannot learn must not break a send that already happened."""
    try:
        cid = str(chat_id or "").strip()
        p = _norm(platform)
        if not cid or p not in PLATFORMS:
            return False
        from .contactos import data as _cd
        db = _cd.load_db()
        people = db.get("contacts") or []
        if contact_id:
            c = next((x for x in people if str(x.get("id") or "") == str(contact_id)), None)
        else:
            c = next((x for x in people for ch in x.get("channels") or []
                      if _norm(ch.get("platform")) == p and str(ch.get("chatId") or "") == cid), None)
        if c is None:
            return False
        chs = c.setdefault("channels", [])
        row = next((ch for ch in chs if _norm(ch.get("platform")) == p), None)
        if row is None:
            row = {"platform": p, "handle": cid, "chatId": cid, "source": "observed", "volume": 0}
            chs.append(row)
        elif str(row.get("chatId") or "") != cid and contact_id:
            row["chatId"] = cid
            logger.info(f"directory: {c.get('name')} → {p}:{cid}")
        row["volume"] = int(row.get("volume") or 0) + 1
        row["last_seen"] = float(ts or time.time())
        _cd.store.save(_cd.WIDGET_ID, db)
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

    Order, each step only when the previous one has nothing: the contact holding this conversation → the contact
    whose phone/address the id carries → the platform's display name (`fallback`) → the bare id. A contact match
    must be UNIQUE: two rows with the same number is an ambiguity, and the platform's name is then more honest."""
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
