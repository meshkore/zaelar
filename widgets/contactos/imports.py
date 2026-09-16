"""widgets/contactos/imports.py — bringing a directory IN from somewhere else, and folding it into ours.

Extracted from `data.py` for the same reason `gcontacts.py` was (V2-699): the data layer must stay
readable, and a matcher that grows a key per source is the file nobody opens twice. Nothing here imports
`data` at module scope.

## The rule the operator set (V2-714, 2026-09-16)

> «Hacemos solo import. Idealmente import continuo. En local los contactos son editables y se pueden
> ocultar, se quedan mapeados a las plataformas, pero ya no se modifican más desde el conector.»

So **continuous import means continuous DISCOVERY, not continuous rewriting**. Every pass brings what we
did not have; a row that already exists here is never overwritten again. There is no push, no
`authoritative`, no «whoever touched it last wins» — that is Google's contract (V2-699) and it stays
Google's, in `gcontacts.py`.

Two things are still ADDED to an existing row, and they are additions rather than modifications: a new
CHANNEL and a new GROUP MEMBERSHIP. Without them, «write to Iván on Telegram» stops working the month he
opens a Telegram account — which is the whole point of this import. Nothing that already has a value is
ever touched.

## Hiding, and why it beats deleting

A row can be hidden (`hidden: true`): it leaves the directory, the suggestions and the reachable set, and
**it keeps its mapping**. That mapping is the entire reason to hide instead of delete — without it the
next pass re-imports the person and he has to hide them again forever. Deleting still exists and is still
LOCAL: neither Telegram nor WhatsApp has an address-book write API, so nothing we do here ever reaches
them, and the card says so instead of letting him find out.

## What a source hands us

A connector normalises to these two shapes and NEVER writes to the store (the boundary `gcontacts.py`
already keeps):

    contact = {"name", "kind"?, "phone"?, "email"?, "city"?, "notes"?, "avatar"?,
               "groups": [label…]?, "channels": [{"platform", "handle"?, "chatId"?}…]?,
               "externalIds": {"<source>": "<id>"}}

    group   = {"name", "platform", "subtype": "group"|"channel"|"cluster",
               "externalIds": {...}, "channels": [...]?, "members": [contact…]}
"""
from __future__ import annotations

import re
import time
import unicodedata

#: Sources this module knows how to fold in. Google keeps its own two-way sync in `gcontacts.py`; these
#: are the IMPORT-ONLY ones.
SOURCES = ("telegram", "whatsapp", "meshkore")


def _norm(s) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def phone_key(v) -> str:
    """A phone reduced to what makes it AN ACCOUNT, so two spellings of one number match (V2-714).

    This is the strongest key that exists between Google, Telegram and WhatsApp — a WhatsApp JID literally
    IS a phone number — and it is what makes «the Iván in my Google contacts» and «the Iván in my Telegram»
    one person instead of two rows he has to reconcile by hand.

    Digits only, and compared by their LAST NINE: nobody stores the same number the same way twice
    («+34 600 11 22 33», «600112233», «0034600112233»), and the national part is what stays constant.
    Nine keeps two different subscribers apart in every numbering plan we ship to, while eight would start
    colliding. Under nine digits it is not an account — a extension or a short code — and it returns "",
    which never matches anything rather than matching everything.
    """
    d = re.sub(r"\D+", "", str(v or ""))
    return d[-9:] if len(d) >= 9 else ""


def _ext(c: dict) -> dict:
    e = c.get("externalIds")
    return e if isinstance(e, dict) else {}


def match(contacts: list[dict], inc: dict) -> dict | None:
    """Which existing row this imported person IS, or None for somebody new.

    Five keys, in descending order of how much they PROVE — the order is the whole point, because each one
    can be right while the ones below it are wrong:

      1. `externalIds[source]` — the same row we imported last time. Survives him renaming the person here,
         and it is what makes a hidden contact stay hidden instead of coming back every pass.
      2. the PHONE, reduced to an account (`phone_key`). Google↔WhatsApp↔Telegram all carry it, and it is
         the key that actually unifies them.
      3. the EMAIL, wherever it lives — the stored field or an email channel. An address is an account.
      4. a CHANNEL that is already ours: `@mushikin` on Telegram is one person, whatever he is called here.
         Asked through `_same_channel` so this agrees with `set_channel` and with V2-693's own rule.
      5. name + city, and then the name ALONE when exactly one contact carries it — `add_contact`'s rule,
         so the two doors agree. It stops at two: adding a duplicate he can merge beats silently folding
         two people into one, which he cannot undo.

    ⚠️ What is deliberately NOT a key: WhatsApp's `notify`, the nickname the OTHER person set for
    themselves. It changes whenever they feel like it and two strangers share it all the time. It fills in
    a blank name and never decides an identity.
    """
    ids = _ext(inc)
    for src, val in ids.items():
        v = str(val or "").strip()
        if not v:
            continue
        for c in contacts:
            if str(_ext(c).get(src) or "").strip() == v:
                return c

    ph = phone_key(inc.get("phone"))
    if ph:
        for c in contacts:
            if phone_key(c.get("phone")) == ph:
                return c

    mail = _norm(inc.get("email"))
    if mail:
        for c in contacts:
            if _norm(c.get("email")) == mail:
                return c
            for ch in c.get("channels") or []:
                if str(ch.get("platform")) == "email" and _norm(ch.get("handle")) == mail:
                    return c

    rows = [r for r in (inc.get("channels") or []) if isinstance(r, dict) and r.get("platform")]
    if rows:
        from .data import _owner_of_channel
        owner = _owner_of_channel(contacts, rows)
        if owner is not None:
            return owner

    nm, city = _norm(inc.get("name")), _norm(inc.get("city"))
    if not nm:
        return None
    for c in contacts:
        if _norm(c.get("name")) == nm and _norm(c.get("city")) == city:
            return c
    same = [c for c in contacts if _norm(c.get("name")) == nm]
    return same[0] if len(same) == 1 else None


#: Fields an import may FILL IN when they are empty here. It may never change one that has a value — that
#: is the operator's rule, and the reason there is no `authoritative` flag anywhere in this module.
_FILLABLE = ("city", "address", "phone", "email", "notes", "avatar")


def merge_contacts(db: dict, rows: list[dict], *, source: str) -> dict:
    """Fold imported people in. Returns counts; NEVER overwrites a value that is already here.

    A hidden row is matched and left hidden: the mapping is what stops the next pass resurrecting somebody
    he removed from his sight on purpose.
    """
    from . import data as _d
    contacts = db.setdefault("contacts", [])
    today = time.strftime("%Y-%m-%d")
    added = filled = unchanged = 0
    for inc in rows or []:
        name = str(inc.get("name") or "").strip()
        if not name:
            continue                        # a row with no name cannot be referenced, listed or spoken
        c = match(contacts, inc)
        if c is None:
            cid = f"c{db.get('next_id', 1)}"
            db["next_id"] = int(db.get("next_id", 1)) + 1
            c = {"id": cid, "kind": _d._kind(inc.get("kind")), "name": name,
                 "city": inc.get("city", ""), "address": inc.get("address", ""),
                 "phone": inc.get("phone", ""), "email": inc.get("email", ""),
                 "notes": inc.get("notes", ""), "avatar": inc.get("avatar", ""),
                 "groups": list(inc.get("groups") or []), "favorite": False,
                 "channels": [], "preferred": "", "parentId": "", "members": [],
                 "hidden": False, "created": today, "updated": today,
                 "source": source, "externalIds": dict(_ext(inc))}
            contacts.append(c)
            for row in inc.get("channels") or []:
                _d._merge_channel(c, _d._channel_row(row) or {})
            c["channels"] = [ch for ch in c.get("channels") or [] if ch.get("platform")]
            added += 1
            continue
        touched = False
        for k in _FILLABLE:
            if inc.get(k) and not str(c.get(k) or "").strip():
                c[k] = inc[k]
                touched = True
        # …and the two ADDITIONS the rule allows. A way to reach him is not a field he wrote.
        for row in inc.get("channels") or []:
            r = _d._channel_row(row)
            if r and not any(_d._same_channel(ch, r) for ch in c.get("channels") or []):
                _d._merge_channel(c, r)
                touched = True
        for g in inc.get("groups") or []:
            if _norm(g) not in {_norm(x) for x in c.get("groups") or []}:
                c.setdefault("groups", []).append(g)
                touched = True
        for src, val in _ext(inc).items():
            if val and not c.setdefault("externalIds", {}).get(src):
                c["externalIds"][src] = val
                touched = True
        if touched:
            c["updated"] = today             # NOT `_touch`: an import filling a blank is not him deciding
            filled += 1
        else:
            unchanged += 1
    return {"added": added, "filled": filled, "unchanged": unchanged, "read": len(rows or [])}


def merge_groups(db: dict, rows: list[dict], *, source: str) -> dict:
    """Fold imported GROUPS in — a Telegram/WhatsApp group chat, a Telegram channel, a MeshKore cluster.

    A group is a `kind`, not a label (V2-714). `data.py` has warned since V2-523 that a group LABEL
    («restaurantes») says how he files things while a `kind` says what the entry IS, and a group chat is
    the second: it has identity, it has members, it comes from a platform and **you can write to it**.
    Putting it in the label field would be exactly the confusion that comment exists to prevent.

    Members are merged as contacts FIRST (so the person in two groups is one row, through the same keys as
    everybody else) and the group then stores their local ids. Membership lives on the GROUP because that
    is where it lives on all three platforms — the group has members, the person does not have groups.

    A broadcast channel enumerates no members. It arrives with none, and the card says «sin miembros» —
    an empty list that means «we cannot know» must not look like one that means «nobody».
    """
    from . import data as _d
    contacts = db.setdefault("contacts", [])
    today = time.strftime("%Y-%m-%d")
    added = filled = unchanged = 0
    for inc in rows or []:
        name = str(inc.get("name") or "").strip()
        if not name:
            continue
        member_rows = [m for m in (inc.get("members") or []) if isinstance(m, dict)]
        if member_rows:
            merge_contacts(db, member_rows, source=source)
        member_ids, seen = [], set()
        for m in member_rows:
            hit = match(contacts, m)
            if hit is not None and hit["id"] not in seen:
                seen.add(hit["id"])
                member_ids.append(hit["id"])
        g = match(contacts, inc)
        if g is None:
            gid = f"c{db.get('next_id', 1)}"
            db["next_id"] = int(db.get("next_id", 1)) + 1
            g = {"id": gid, "kind": "group", "name": name, "city": "", "address": "",
                 "phone": "", "email": "", "notes": inc.get("notes", ""), "avatar": inc.get("avatar", ""),
                 "groups": [], "favorite": False, "channels": [], "preferred": "", "parentId": "",
                 "members": member_ids, "membersKnown": bool(member_rows) or inc.get("subtype") != "channel",
                 "platform": str(inc.get("platform") or source), "subtype": str(inc.get("subtype") or "group"),
                 "hidden": False, "created": today, "updated": today,
                 "source": source, "externalIds": dict(_ext(inc))}
            contacts.append(g)
            for row in inc.get("channels") or []:
                _d._merge_channel(g, _d._channel_row(row) or {})
            g["channels"] = [ch for ch in g.get("channels") or [] if ch.get("platform")]
            added += 1
            continue
        touched = False
        # A group that already exists keeps its name (he may have renamed it) and GAINS members: somebody
        # joining is new information, not an edit of his.
        known = set(g.setdefault("members", []))
        for mid in member_ids:
            if mid not in known:
                known.add(mid)
                g["members"].append(mid)
                touched = True
        for row in inc.get("channels") or []:
            r = _d._channel_row(row)
            if r and not any(_d._same_channel(ch, r) for ch in g.get("channels") or []):
                _d._merge_channel(g, r)
                touched = True
        for src, val in _ext(inc).items():
            if val and not g.setdefault("externalIds", {}).get(src):
                g["externalIds"][src] = val
                touched = True
        if touched:
            g["updated"] = today
            filled += 1
        else:
            unchanged += 1
    return {"added": added, "filled": filled, "unchanged": unchanged, "read": len(rows or [])}


def absorb(db: dict, payload: dict, *, source: str) -> dict:
    """One pass of one source: `{"contacts": [...], "groups": [...]}` → counts. The single door every
    importer comes through, so a new platform adds a normaliser and nothing else."""
    people = merge_contacts(db, payload.get("contacts") or [], source=source)
    groups = merge_groups(db, payload.get("groups") or [], source=source)
    return {"contacts": people, "groups": groups,
            "added": people["added"] + groups["added"],
            "filled": people["filled"] + groups["filled"]}
