"""The group and linked-agent actions of the contacts card (V2-854 F1); `data.ACTIONS` maps the names to them.

Same shape as `actions.py` (every module-level name of `data` read through it). Membership itself lives in
`groups.py`: a label on the contact, and `favorite` for the native favorites.
"""
from __future__ import annotations

from . import data as _d
from . import model


def _group_of(db, payload):
    return _d._groups.find(db, payload.get("groupId") or payload.get("group") or payload.get("name"))


def _no_group(db, payload) -> dict:
    names = ", ".join(str(r.get("name")) for r in _d._groups.sync(db))
    return {"ok": False, "error": f"no tengo el grupo «{payload.get('groupId') or payload.get('group') or ''}» — "
                                  f"los que hay: {names}. Para uno nuevo, create_group"}


def _group_result(db, q, g, **extra) -> dict:
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"group": {**g, "members": len(_d._groups.members(db, g))}, **extra}})
    return d


def _a_create_group(action, payload, q, db, contacts, now) -> dict:
    """«Créame un grupo con los padres del colegio» — a group of his, optionally with its first members."""
    name = _d.re.sub(r"\s+", " ", str(payload.get("name") or payload.get("group") or "")).strip()
    if not name:
        return {"ok": False, "error": "create_group necesita el nombre del grupo (`name`)"}
    g, created = _d._groups.create(db, name)
    added = [c for c in _contacts_of(db, payload) if _d._groups.set_member(g, c, True)]
    for c in added:
        _d._touch(c, now)
    _d.store.save(_d.WIDGET_ID, db)
    return _group_result(db, q, g, created=created, added=[_d._public(c) for c in added])


def _a_rename_group(action, payload, q, db, contacts, now) -> dict:
    g = _d._groups.find(db, payload.get("groupId") or payload.get("group"))
    new = str(payload.get("name") or "").strip()
    if not g:
        return _no_group(db, payload)
    if g.get("native"):
        return {"ok": False, "error": f"«{g['name']}» es un grupo de serie: no se renombra (crea uno suyo)"}
    if not new:
        return {"ok": False, "error": "rename_group necesita el nombre nuevo (`name`)"}
    other = _d._groups.find(db, new)
    if other is not None and other is not g:
        return {"ok": False, "error": f"ya hay un grupo «{other['name']}»"}
    for c in _d._groups.members(db, g):
        _d._touch(c, now)
    _d._groups.rename(db, g, new)
    _d.store.save(_d.WIDGET_ID, db)
    return _group_result(db, q, g)


def _a_delete_group(action, payload, q, db, contacts, now) -> dict:
    """The group goes; its members stay in the directory."""
    g = _group_of(db, payload)
    if not g:
        return _no_group(db, payload)
    if g.get("native"):
        return {"ok": False, "error": f"«{g['name']}» es un grupo de serie: no se borra"}
    for c in _d._groups.members(db, g):
        _d._touch(c, now)
    n = _d._groups.delete(db, g)
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"deleted": g, "members_kept": n}})
    return d


def _contacts_of(db, payload) -> list[dict]:
    ids = payload.get("contactIds")
    ids = (list(ids) if isinstance(ids, (list, tuple)) else str(ids or "").split(",")) + [payload.get("contactId")]
    out = []
    for cid in ids:
        c = _d._find(db, str(cid or "").strip())
        if c is not None and c not in out:
            out.append(c)
    return out


def _a_add_to_group(action, payload, q, db, contacts, now) -> dict:
    """Members in or (`remove: true`) out — one or several contacts at once; a contact may be in several groups."""
    g = _group_of(db, payload)
    if not g:
        return _no_group(db, payload)
    people = _contacts_of(db, payload)
    if not people:
        return {"ok": False, "error": "add_to_group necesita a quién: `contactId` o `contactIds`"}
    on = not _d._truthy(payload.get("remove"), default=False)
    changed = [c for c in people if _d._groups.set_member(g, c, on)]
    for c in changed:
        model.normalize(c)
        _d._touch(c, now)
    if changed:
        _d.store.save(_d.WIDGET_ID, db)
    return _group_result(db, q, g, **{"added" if on else "removed": [_d._public(c) for c in changed]})


def _a_set_agent(action, payload, q, db, contacts, now) -> dict:
    """An agent this person or company is reachable through (its id and cluster) — kept for a direct conversation
    between agents later; nothing reads it to act yet. `remove: true` unlinks it."""
    c = _d._find(db, payload.get("contactId"))
    if not c:
        return {"ok": False, "error": "set_agent necesita el `contactId`"}
    if model.kind(c.get("kind")) not in model.AGENT_HOLDERS:
        return {"ok": False, "error": "solo una persona o una empresa lleva agentes vinculados"}
    row = model.agent_row(payload)
    if not row:
        return {"ok": False, "error": "set_agent necesita el `agent_id` (y su `cluster` si lo tiene)"}
    keep = [a for a in c.get("agents") or [] if (a.get("agent_id"), a.get("cluster")) != (row["agent_id"], row["cluster"])]
    c["agents"] = keep if _d._truthy(payload.get("remove"), default=False) else keep + [row]
    model.normalize(c)
    _d._touch(c, now)
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"contact": _d._public(c)}})
    return d
