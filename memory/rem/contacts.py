"""REM phase · one person, several records (V2-854 F3).

His address book is fed by several sources (an imported Google book, the chats a messaging connector sees), and one
person arrives as several records: a WhatsApp chat with a nickname, a Google entry with an e-mail, a second Google
entry made from that e-mail. Nothing here deletes or merges a record: records of one person are LINKED (the child
gets `parentId` = the record that stands for her), through the contacts card's own door, which the caller injects.

The rule is pure (no store, no widget import — memory imports no card): it reads the records and returns
  · `links`     — the HIGH-confidence ones, applied automatically: two records that share an identifier only one
                  person has (a phone, an e-mail, a chat id) AND whose names do not contradict it;
  · `proposals` — the rest, listed for him and never applied: a shared identifier with names that disagree, an
                  identifier three or more records share (a family line, a switchboard), or two near-identical
                  names with no identifier in common (a near spelling across sources; the same letters in one).

Thresholds are rules with readers, declared here once: `PHONE_KEY_DIGITS`, `SHARED_BY_MAX`, `NEAR_NAME`.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

#: A phone is compared on its last digits, so the same number with and without its country prefix is one key.
#: Shorter numbers (extensions, short codes) identify nobody.
PHONE_KEY_DIGITS = 8
#: An identifier held by MORE records than this is shared (a home line, a switchboard, a group): proposal only.
SHARED_BY_MAX = 2
#: Two full names at or above this similarity are «near-identical» (a proposal when nothing else ties them).
NEAR_NAME = 0.92
#: Kinds a record of ONE identity can have. A group or an agent is many people or none: never unified.
_UNIFIABLE = ("person", "company", "place")


def _fold(s) -> str:
    n = unicodedata.normalize("NFKD", str(s or ""))
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    return re.sub(r"[^0-9a-z]+", " ", n).strip()


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _fold(a), _fold(b)).ratio()


def identifiers(c: dict) -> set[str]:
    """Every value that names this record's owner: phones (by their last digits), e-mails, chat ids and handles."""
    out: set[str] = set()
    phones = [c.get("phone")] + [p.get("value") for p in c.get("phones") or [] if isinstance(p, dict)]
    for p in phones:
        d = re.sub(r"\D", "", str(p or ""))
        if len(d) >= PHONE_KEY_DIGITS:
            out.add("tel:" + d[-PHONE_KEY_DIGITS:])
    emails = [c.get("email")] + [e.get("value") for e in c.get("emails") or [] if isinstance(e, dict)]
    out |= {"mail:" + str(e).strip().lower() for e in emails if "@" in str(e or "")}
    for ch in c.get("channels") or []:
        if not isinstance(ch, dict):
            continue
        plat = str(ch.get("platform") or "").strip().lower()
        for v in (ch.get("chatId"), ch.get("handle")):
            if str(v or "").strip():
                out.add(f"{plat}:{str(v).strip().lower()}")
    ext = c.get("externalIds") if isinstance(c.get("externalIds"), dict) else {}
    out |= {f"{str(k).lower()}:{str(v).strip().lower()}" for k, v in ext.items() if str(v or "").strip()}
    return out


def names_agree(a: str, b: str) -> bool:
    """Do two names fit ONE person? Every word of the shorter name is a word of the longer (a near spelling of a word
    counts). A shared first name is not enough («Toni» and «Toni's mum» share a home line), and neither is a near
    spelling of the WHOLE name («Ann, Summer Camp» / «Joe, Summer Camp» share a switchboard and most letters). A
    side with no name of its own (digits, an address) contradicts nothing."""
    fa, fb = _fold(a), _fold(b)
    if not re.search(r"[a-z]", fa) or not re.search(r"[a-z]", fb):
        return True
    if fa.replace(" ", "") == fb.replace(" ", ""):
        return True
    short, long_ = sorted((fa.split(), fb.split()), key=len)
    return all(any(w == x or (len(w) >= 4 and _ratio(w, x) >= 0.8) for x in long_) for w in short)


def _near(a: dict, b: dict) -> bool:
    fa, fb = _fold(a.get("name")), _fold(b.get("name"))
    if fa.replace(" ", "") == fb.replace(" ", ""):
        return True
    return (str(a.get("source") or "") != str(b.get("source") or "") and len(fa.split()) >= 2
            and len(fb.split()) >= 2 and _ratio(fa, fb) >= NEAR_NAME)


def _richness(c: dict) -> tuple:
    """Which record of a cluster stands for the person: his mark first (favorite, a word or relation he gave),
    then the one that reaches her most ways, then the oldest."""
    num = re.sub(r"\D", "", str(c.get("id") or "")) or "0"
    return (bool(c.get("favorite")), bool(c.get("aliases") or c.get("relation")), len(identifiers(c)), -int(num))


def same_person(contacts: list[dict]) -> dict:
    """`{links: [{child, parent, reason}], proposals: [{ids, reason}]}` over these records. Idempotent: a record
    already linked to the one that stands for its cluster yields no link."""
    rows = [c for c in contacts or [] if isinstance(c, dict) and c.get("id")
            and str(c.get("kind") or "person") in _UNIFIABLE]
    by_id = {str(c["id"]): c for c in rows}
    holders: dict[str, list[str]] = {}
    for c in rows:
        for key in identifiers(c):
            holders.setdefault(key, []).append(str(c["id"]))
    parent = {cid: cid for cid in by_id}

    def root(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    proposals: dict[tuple, dict] = {}
    for key, ids in holders.items():
        ids = sorted(set(ids))
        if len(ids) < 2:
            continue
        if len(ids) > SHARED_BY_MAX:
            proposals.setdefault(tuple(ids), {"ids": ids, "reason": f"shared:{key.split(':')[0]}"})
            continue
        a, b = (by_id[i] for i in ids)
        if a.get("kind") != b.get("kind") or not names_agree(a.get("name"), b.get("name")):
            proposals.setdefault(tuple(ids), {"ids": ids, "reason": f"names-differ:{key.split(':')[0]}"})
            continue
        parent[root(ids[0])] = root(ids[1])
    # Near-identical names with nothing else in common: his call. Across sources a near spelling of the full name;
    # within one source only the same letters (an entry made from an address, «ana.ruiz» beside «Ana Ruiz»).
    blocks: dict[str, list[dict]] = {}
    for c in rows:
        f = _fold(c.get("name"))
        if c.get("kind") == "person" and len(f.replace(" ", "")) >= 6:
            blocks.setdefault(f[:3], []).append(c)
    for group in blocks.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                ia, ib = str(a["id"]), str(b["id"])
                if root(ia) == root(ib) or not _near(a, b):
                    continue
                ids = sorted((ia, ib))
                proposals.setdefault(tuple(ids), {"ids": ids, "reason": "near-name"})
    clusters: dict[str, list[dict]] = {}
    for cid in by_id:
        clusters.setdefault(root(cid), []).append(by_id[cid])
    links: list[dict] = []
    held: list[dict] = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        ids = {str(m["id"]) for m in members}
        # A record the others already hang from stands for the cluster (a previous pass chose it); else the richest.
        pointed = [m for m in members if any(str(o.get("parentId") or "") == str(m["id"]) for o in members)]
        head = max(pointed or members, key=_richness)
        for m in members:
            if m is head or str(m.get("parentId") or "") == str(head["id"]):
                continue
            if str(m.get("parentId") or "") and str(m.get("parentId")) not in ids:
                # Already hanging from someone outside (her company): never re-parented, his call.
                held.append({"ids": sorted((str(m["id"]), str(head["id"]))), "reason": "has-parent"})
                continue
            links.append({"child": str(m["id"]), "parent": str(head["id"]), "reason": "shared-identifier"})
    # A proposal whose records the links already joined is settled.
    out = [p for p in proposals.values() if len({root(i) for i in p["ids"]}) > 1] + held
    return {"links": links, "proposals": sorted(out, key=lambda p: p["ids"])}
