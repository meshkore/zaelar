"""The people of his address book, in his memory (V2-854 F3).

Three duties, one module of the memory's single writer:

  · **The index.** Each record the contacts card manages is ONE pill of `kind='contact'`, `slot='contact:<id>'`: a
    structured line (name and the other names he or a chat uses, kind, relation, groups, the PLATFORMS she is
    reachable on, notes) — never a phone number or an address, because a pill is text a model reads. The slot makes a
    changed record supersede its old line; a record that left the book (or that he hid) has its line invalidated.
    `sync()` is a bounded, change-detecting pass (only lines that differ are written, closest people first), run by
    REM and before every `who()`. Contact pills live in their own retriever LANE, so thousands of them never crowd
    his own recall, and carry no vector (read by their words, never paid an embedding for).
  · **Who a description means.** `who("the girl from the guitar course last year")` searches his memory (his facts and
    episodes, the messages he received) and the contact lane, and returns candidate contact ids, each with the
    evidence that put it there. A NAME is the contacts resolver's job (`widgets/directory.resolve`); this is the
    other half — the description.
  · **What he said about a person.** A distilled fact that names a person of his book («Noemí es mi mujer», «tiene
    una tienda que se llama X») carries `person = {name, relation, known_as}`; `link_fact` writes it ONCE on that
    contact through the card's own door (`set_alias`) when exactly one contact is that name.

And `rem_pass()` — REM's unification of one person's records (`memory/rem/contacts.py` decides; this applies the
high-confidence links through `link_contact` and keeps the rest as proposals for him).
"""
from __future__ import annotations

import re

from loguru import logger

WIDGET_ID = "contactos"
SLOT_PREFIX = "contact:"
KIND = "contact"
#: Lines written per sync pass: the first index of a large book is spread over passes instead of flooding the queue.
SYNC_BATCH = 300
#: Links REM applies per pass (each is one save of the book); the rest wait for the next sleep.
LINKS_PER_PASS = 25
#: Proposals kept for him (oldest dropped).
PROPOSALS_MAX = 200
PROPOSALS_KEY = "contacts.unify.proposals"
#: A first name shared by more contacts than this says nothing about which one a memory meant.
FIRST_NAME_MAX = 10

_REDACT = re.compile(r"\S+@\S+|\+?\d[\d\s().-]{4,}\d")


# ── the store (read only; every write goes through the card's door) ───────────────────────────────────────
def _book() -> list[dict]:
    try:
        from widgets import store
        if not store.exists(WIDGET_ID):
            return []
        return [c for c in store.load(WIDGET_ID, {}).get("contacts") or [] if isinstance(c, dict) and c.get("id")]
    except Exception as e:  # noqa: BLE001 — an unreadable book indexes nothing, and says so
        logger.debug(f"memory_agent.contacts: book unreadable ({e!r})")
        return []


def _door(action: str, payload: dict) -> dict:
    from widgets.contactos import data as _card
    return _card.apply_action(action, payload) or {}


def _fold(s) -> str:
    from widgets.textmatch import fold
    return fold(s)


def names_of(c: dict) -> list[str]:
    """Every name a record is known by: its own, his words for her, and the name each of her chats shows."""
    out: list[str] = []
    for n in [c.get("name")] + list(c.get("aliases") or []) + [ch.get("name") for ch in c.get("channels") or []
                                                                if isinstance(ch, dict)]:
        n = str(n or "").strip()
        if n and _fold(n) not in {_fold(x) for x in out}:
            out.append(n)
    return out


def _platforms(c: dict) -> list[str]:
    plats = [str(ch.get("platform") or "") for ch in c.get("channels") or [] if isinstance(ch, dict)]
    if c.get("email") or c.get("emails"):
        plats.append("email")
    if c.get("phone") or c.get("phones"):
        plats.append("phone")
    return sorted({p for p in plats if p})


# ── the index ─────────────────────────────────────────────────────────────────────────────────────────────
def _clean(s) -> str:
    """A field as it may appear in a line a model reads: no phone number, no address (some names ARE one)."""
    return re.sub(r"\s+", " ", _REDACT.sub("", str(s or ""))).strip(" ,;·-")


def entity(c: dict, by_id: dict | None = None) -> dict | None:
    """The pill for one record, or None for one that is not indexed (hidden by him, or no name once its numbers and
    addresses are taken out — a record only a number names is the name resolver's, never a line)."""
    names = [n for n in (_clean(x) for x in names_of(c)) if n]
    if c.get("hidden") or not names:
        return None
    parent = (by_id or {}).get(str(c.get("parentId") or "")) or {}
    head = f"{names[0]} — {c.get('kind') or 'person'}"
    parts = [head] + (["also: " + ", ".join(names[1:])] if names[1:] else [])
    parts += [str(c["relation"])] if c.get("relation") else []
    parts += ["groups: " + ", ".join(_clean(g) for g in c["groups"])] if c.get("groups") else []
    parts += [f"linked to: {_clean(parent['name'])}"] if _clean(parent.get("name")) else []
    parts += [_clean(c["city"])] if _clean(c.get("city")) else []
    plats = _platforms(c)
    parts += ["reachable on: " + ", ".join(plats)] if plats else []
    parts += ["favorite"] if c.get("favorite") else []
    parts += ["notes: " + _clean(c["notes"])[:240]] if _clean(c.get("notes")) else []
    text = " · ".join(parts).replace(head, f"{names[0]} [{SLOT_PREFIX}{c['id']}] — {c.get('kind') or 'person'}", 1)
    meta = {"source": "contacts", "entity": names[0], "contact_id": str(c["id"]),
            "contact_kind": c.get("kind") or "person", "names": names, "relation": c.get("relation") or "",
            "groups": [_clean(g) for g in c.get("groups") or []], "channels": plats,
            "parent_id": str(c.get("parentId") or "")}
    return {"text": text, "slot": f"{SLOT_PREFIX}{c['id']}", "meta": meta}


def _closeness(c: dict) -> tuple:
    seen = max([float(ch.get("last_seen") or 0) for ch in c.get("channels") or [] if isinstance(ch, dict)] or [0.0])
    return (bool(c.get("favorite")), bool(c.get("aliases") or c.get("relation")), seen)


def sync(limit: int = SYNC_BATCH) -> dict:
    """One bounded pass: write the lines that changed (closest people first), invalidate the ones whose record is
    gone. `{written, removed, pending}`; `pending` > 0 means the next pass carries on."""
    from memory import api as memory
    book = _book()
    by_id = {str(c["id"]): c for c in book}
    have = {r["slot"]: r["text"] for r in memory.by_slot_prefix(SLOT_PREFIX, limit=100_000)}
    want = {}
    for c in sorted(book, key=_closeness, reverse=True):
        e = entity(c, by_id)
        if e:
            want[e["slot"]] = e
    removed = sum(memory.clear_slot(slot) for slot in have if slot not in want)
    todo = [e for slot, e in want.items() if have.get(slot) != e["text"]]
    for e in todo[:limit]:
        memory.write(e["text"], kind=KIND, level="long", importance=0.4, slot=e["slot"], meta=e["meta"])
    return {"written": min(len(todo), limit), "removed": removed, "pending": max(0, len(todo) - limit)}


# ── who a description means ───────────────────────────────────────────────────────────────────────────────
def _name_index(book: list[dict]) -> tuple[dict, dict]:
    """(full name → ids, first name → ids), folded; names under three letters name nobody."""
    full: dict[str, set] = {}
    first: dict[str, set] = {}
    for c in book:
        if c.get("hidden"):
            continue
        for n in names_of(c):
            f = _fold(n)
            if len(f) >= 3:
                full.setdefault(f, set()).add(str(c["id"]))
                head = f.split(" ")[0]
                if " " in f and len(head) >= 3:
                    first.setdefault(head, set()).add(str(c["id"]))
    return full, first


def _named_in(text: str, full: dict, first: dict) -> dict[str, float]:
    """The contacts a memory's text names, each with how surely: a whole name or his word for her is sure; a first
    name alone is shared among everyone who has it, and says nothing past `FIRST_NAME_MAX` people."""
    hay = f" {_fold(text)} "
    out: dict[str, float] = {}
    for f, ids in full.items():
        if f" {f} " in hay:
            for i in ids:
                out[i] = max(out.get(i, 0.0), 1.0 / len(ids))
    for f, ids in first.items():
        if len(ids) <= FIRST_NAME_MAX and f" {f} " in hay:
            for i in ids:
                out[i] = max(out.get(i, 0.0), 0.5 / len(ids))
    return out


def who(description: str, *, limit: int = 3) -> list[dict]:
    """The contacts `description` can mean, best first: `[{contact_id, name, score, evidence: [{memory_id, text,
    why}]}]`, `why` ∈ card (her own line matched) · linked (a memory written about her) · named (a memory that
    names her). Empty when nothing in his memory points at anyone — the caller asks him, never guesses."""
    if not str(description or "").strip():
        return []
    try:
        sync()
    except Exception as e:  # noqa: BLE001 — a failed pass still reads what is indexed
        logger.debug(f"memory_agent.contacts: sync before who failed ({e!r})")
    from memory import api as memory
    book = _book()
    by_id = {str(c["id"]): c for c in book if not c.get("hidden")}
    full, first = _name_index(book)
    score: dict[str, float] = {}
    evidence: dict[str, list] = {}

    def note(cid: str, w: float, hit: dict, why: str) -> None:
        if cid not in by_id or w <= 0:
            return
        score[cid] = score.get(cid, 0.0) + w
        evidence.setdefault(cid, []).append({"memory_id": hit["id"], "text": str(hit.get("text") or "")[:240],
                                             "why": why})

    # Read by the description's WORDS, both halves: the lexical channel alone (`search(lexical_only)` falls back to
    # a substring of the first word when FTS finds nothing, and «la» is inside every «Laura»), and his memories by the
    # full recall but counted only when a word of the description is in them — a vector channel always returns its
    # nearest rows, relevant or not, and the person a far episode names is not the one he described. The memory is
    # monolingual (his language), so his words are the ones it holds. Her own line carries no vector at all.
    card_ids = memory.lexical_ids(description, k=8, lane="contacts")
    card_prov = memory.provenance(card_ids)
    for pos, mid in enumerate(card_ids):
        cid = str((card_prov.get(mid) or {}).get("slot") or "").removeprefix(SLOT_PREFIX)
        line = (entity(by_id[cid], by_id) or {}).get("text", "") if cid in by_id else ""
        note(cid, 1.0 / (1 + pos), {"id": mid, "text": line}, "card")
    worded = set(memory.lexical_ids(description, k=64, lane="all"))
    recall = memory.query(description, limit=8, lane="all", reinforce_used=False)["memories"]
    hits = [h for h in recall if h["id"] in worded]
    prov = memory.provenance([h["id"] for h in hits])
    for hit in hits:
        p = prov.get(hit["id"]) or {}
        s = float(hit.get("score") or 0.0)
        if p.get("contact_id"):
            note(str(p["contact_id"]), s, hit, "linked")
            continue
        for cid, w in _named_in(f"{hit.get('text') or ''} {p.get('entity') or ''}", full, first).items():
            note(cid, s * w, hit, "named")
    ranked = sorted(score, key=lambda i: -score[i])[:max(1, int(limit))]
    return [{"contact_id": i, "name": by_id[i].get("name"), "score": round(score[i], 4),
             "evidence": evidence[i][:3]} for i in ranked]


# ── what he said about a person ───────────────────────────────────────────────────────────────────────────
def relations() -> tuple[str, ...]:
    """Who a person can be to him — the contacts card's declared vocabulary."""
    try:
        from widgets.contactos import actions as _acts
        return _acts.relations()
    except Exception as _e:  # noqa: BLE001
        __import__("loguru").logger.debug(f"memory_agent.contacts: unreadable, nothing returned — {type(_e).__name__}: {_e}")
        return ()


def link_fact(person: dict) -> str:
    """A fact he said names `person` ({name, relation, known_as}). When exactly ONE contact is that name, write on it
    what is new — the relation, the other name he uses — through the card's door, and return its id (the pill is
    stamped with it). Ambiguous or unknown: nothing is written and nobody is asked."""
    if not isinstance(person, dict) or not str(person.get("name") or "").strip():
        return ""
    try:
        from widgets import directory
        hits = directory.resolve(str(person["name"]), tolerant=False)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"memory_agent.contacts: resolve failed ({e!r})")
        return ""
    if len(hits) != 1:
        return ""
    c = hits[0]
    cid = str(c.get("id") or "")
    rel = str(person.get("relation") or "").strip().lower()
    if rel and rel in relations() and rel != str(c.get("relation") or ""):
        _door("set_alias", {"contactId": cid, "relation": rel})
    known = str(person.get("known_as") or "").strip()
    if known and _fold(known) not in {_fold(n) for n in names_of(c)}:
        _door("set_alias", {"contactId": cid, "alias": known, "source": "learned"})
    return cid


# ── REM: one person, several records ──────────────────────────────────────────────────────────────────────
def unify(*, apply: bool = True) -> dict:
    """Apply the high-confidence links (`LINKS_PER_PASS`), keep the proposals for him. `apply=False` measures."""
    from memory import api as memory
    found = memory.same_person_records(_book())
    linked = 0
    if apply:
        for link in found["links"][:LINKS_PER_PASS]:
            if (_door("link_contact", {"contactId": link["child"], "parentId": link["parent"]}) or {}).get("ok"):
                linked += 1
        memory.kv_set(PROPOSALS_KEY, found["proposals"][-PROPOSALS_MAX:])
    return {"links": len(found["links"]), "linked": linked, "proposals": len(found["proposals"])}


def rem_pass() -> dict:
    """REM's phase: unify first (a link changes the lines), then index."""
    return {"unify": unify(), "index": sync()}


def _register() -> None:
    try:
        from memory import api as memory
        memory.register_sleep_phase("contacts", rem_pass)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"memory_agent.contacts: REM phase not registered ({e!r})")


_register()
