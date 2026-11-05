"""groups.py — his groups as rows with an id, and who is in each (V2-854 F1).

A group is a ROW of the `groups` collection — `{"groupId", "name", "native"}` — so a door can name it, rename it and
delete it like any other row (`widgets/rows.py` reads `db["groups"]`). Membership has ONE owner per group, and it is
the field that already carried it, so every reader of a contact (the filters, the Google mirror, the digest) keeps
reading what it read:

  · his own groups and the native ones that are not favorites → the contact's `groups` labels, matched by the
    group's name (a label IS a membership; renaming a group rewrites the label on its members);
  · the native `favorites` group → the contact's `favorite` field (four modules outside this widget read it).

The native groups (and the relations each one gathers) are DECLARED in the manifest's `native_groups`, in the order
the directory ranks them; nothing here names one. `sync` is idempotent: it seeds the declared natives and turns every
label a contact carries into a row of his own, so a label an import brings later gets its id on the next read.

Never two groups with one name: a name is how a membership is stored.
"""
from __future__ import annotations

import time

from . import model

#: The membership field of the native group that reads `favorite` instead of a label.
FAVORITES = "favorites"


def declared() -> list[dict]:
    """The manifest's `native_groups`, in rank order: `[{"id", "relations": [...]}]`. Unreadable → none."""
    try:
        from widgets import runtime
        rows = (runtime.get("contactos") or {}).get("native_groups") or []
        return [dict(r) for r in rows if isinstance(r, dict) and str(r.get("id") or "").strip()]
    except Exception:  # noqa: BLE001 — no natives declared: his own groups still work
        return []


def native_ids() -> list[str]:
    return [str(r["id"]) for r in declared()]


def sync(db: dict) -> list[dict]:
    """The `groups` rows, made whole: every declared native, then every label a contact carries. Idempotent — run
    on every read; it only ever ADDS rows (a group he deleted takes its label off its members, so it does not
    come back)."""
    rows = [r for r in (db.get("groups") or []) if isinstance(r, dict) and str(r.get("groupId") or "").strip()]
    have = {model.norm(r.get("name")) for r in rows}
    ids = {str(r["groupId"]) for r in rows}
    for nat in declared():
        gid = str(nat["id"])
        if gid not in ids:
            rows.append({"groupId": gid, "name": gid, "native": True})
            ids.add(gid)
            have.add(model.norm(gid))
    for c in db.get("contacts") or []:
        if not isinstance(c, dict):
            continue
        for label in c.get("groups") or []:
            label = str(label or "").strip()
            if label and model.norm(label) not in have:
                rows.append({"groupId": _new_id(db, ids), "name": label, "native": False})
                have.add(model.norm(label))
    db["groups"] = rows
    return rows


def _new_id(db: dict, ids: set) -> str:
    n = int(db.get("next_group_id") or 1)
    while f"g{n}" in ids:
        n += 1
    db["next_group_id"] = n + 1
    ids.add(f"g{n}")
    return f"g{n}"


def find(db: dict, ref) -> dict | None:
    """The group `ref` names: its id, else its name (accent/case-insensitive). None when nothing matches."""
    want = str(ref or "").strip()
    if not want:
        return None
    rows = sync(db)
    return (next((r for r in rows if str(r["groupId"]) == want), None)
            or next((r for r in rows if model.norm(r.get("name")) == model.norm(want)), None))


def is_member(group: dict, contact: dict) -> bool:
    if str(group.get("groupId")) == FAVORITES and group.get("native"):
        return bool(contact.get("favorite"))
    name = model.norm(group.get("name"))
    return bool(name) and name in {model.norm(g) for g in contact.get("groups") or []}


def members(db: dict, group: dict) -> list[dict]:
    return [c for c in db.get("contacts") or [] if isinstance(c, dict) and is_member(group, c)]


def ids_of(db: dict, contact: dict) -> list[str]:
    """Every group this contact is in — a contact may be in several."""
    return [str(g["groupId"]) for g in sync(db) if is_member(g, contact)]


def set_member(group: dict, contact: dict, on: bool) -> bool:
    """Put `contact` in `group` or take it out. False when it changes nothing."""
    if is_member(group, contact) == bool(on):
        return False
    if str(group.get("groupId")) == FAVORITES and group.get("native"):
        contact["favorite"] = bool(on)
        return True
    name = model.norm(group.get("name"))
    labels = [g for g in contact.get("groups") or [] if model.norm(g) != name]
    contact["groups"] = labels + ([str(group.get("name"))] if on else [])
    return True


def create(db: dict, name: str) -> tuple[dict, bool]:
    """A group of his called `name` → (row, created). A name that already is a group returns that group."""
    hit = find(db, name)
    if hit is not None and model.norm(hit.get("name")) == model.norm(name):
        return hit, False
    rows = sync(db)
    row = {"groupId": _new_id(db, {str(r["groupId"]) for r in rows}), "name": str(name).strip(), "native": False,
           "created": time.strftime("%Y-%m-%d")}
    rows.append(row)
    return row, True


def rename(db: dict, group: dict, name: str) -> None:
    """The row's name and the label on every member, in one gesture — the label IS the membership."""
    old = model.norm(group.get("name"))
    for c in db.get("contacts") or []:
        if isinstance(c, dict) and old in {model.norm(g) for g in c.get("groups") or []}:
            c["groups"] = [str(name).strip() if model.norm(g) == old else g for g in c["groups"]]
    group["name"] = str(name).strip()


def delete(db: dict, group: dict) -> int:
    """The row goes and its label leaves every member; the contacts stay. Returns how many members it had."""
    n = 0
    for c in members(db, group):
        n += set_member(group, c, False)
    db["groups"] = [r for r in sync(db) if str(r.get("groupId")) != str(group.get("groupId"))]
    return n


def native_rank(contact: dict, nats: list[dict] | None = None) -> int:
    """Where this contact sits on the declared native scale: the count of natives BELOW its best one (the first
    declared native it belongs to scores highest), 0 when it is in none. A relation counts for the native that
    declares it («partner» → family), so who a person is to him and the group he filed them in are one reading."""
    nats = declared() if nats is None else nats
    rel = model.norm(contact.get("relation"))
    labels = {model.norm(g) for g in contact.get("groups") or []}
    for i, nat in enumerate(nats):
        gid = str(nat["id"])
        hit = (bool(contact.get("favorite")) if gid == FAVORITES
               else model.norm(gid) in labels or (rel and rel in {model.norm(r) for r in nat.get("relations") or []}))
        if hit:
            return len(nats) - i
    return 0
