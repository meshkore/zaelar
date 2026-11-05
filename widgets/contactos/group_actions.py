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


# ── a message to a group, from the card: handed to the conversation, never sent from here (V2-854 F5) ──────────
#
# The card holds no send. «Send a message to this group» becomes HIS typed order in the one conversation — the
# line a screen without the voice types through `POST /api/chat` — so it meets exactly what a spoken order meets:
# the message door's «did he name them», the one consent rule, the channel each person really has. The order is
# written from the voice pack (`contactos.order_*`), in the agent's language, and it shows up in the chat as his line.
#
# Three ways out, chosen by the card BEFORE it calls (it asks him once when the group has no WhatsApp mirror):
#   · `group`  — the group has a WhatsApp chat group of the same name (`groups.mirror_of`): one message, there;
#   · `create` — create that WhatsApp group with the members reachable there, then write in it;
#   · `each`   — one message to each member, by the channel each one has.
# `mirror` with no text only creates the WhatsApp group. The members who cannot be reached that way are named back.

MODES = ("group", "create", "each", "mirror")


def _reachable(c: dict, platform: str = "") -> bool:
    return any(isinstance(ch, dict) and str(ch.get("chatId") or ch.get("handle") or "").strip()
               and (not platform or str(ch.get("platform") or "") == platform)
               for ch in c.get("channels") or []) or (not platform and not model.unclassified(c))


def _hand_over(order: str) -> str:
    """Deliver `order` as a typed line of his into the live session, on the server loop that owns the screens —
    the same door `POST /api/chat` opens. Returns the reason it could not, or "" when it was handed over."""
    from nucleo import runstate
    from voice import screens
    if runstate.stopped():
        return "stopped"
    if not screens.has_session():
        return "no_session"
    from nucleo import dispatch
    loop = dispatch._LOOP
    if loop is None:
        return "no_session"
    loop.call_soon_threadsafe(loop.create_task, screens.deliver_typed(order, ""))
    return ""


def _a_message_group(action, payload, q, db, contacts, now) -> dict:
    """The card's «send a message to this group» / «create it on WhatsApp» — written as his order and handed to the
    conversation. Declared `internal` and `worker: false`: only his click on the card reaches it."""
    from widgets import provenance
    from i18n import langs
    if provenance.who(_d.WIDGET_ID) != "user":
        return {"ok": False, "error": "message_group es un gesto de la tarjeta: la voz manda con mensajeria"}
    g = _group_of(db, payload)
    if not g:
        return _no_group(db, payload)
    text = _d.re.sub(r"\s+", " ", str(payload.get("text") or "")).strip()[:1000]
    mirror = _d._groups.mirror_of(db, g)
    mode = str(payload.get("mode") or ("group" if mirror is not None else "")).strip().lower()
    if mode not in MODES:
        return {"ok": False, "needs": "mode", "error": "sin grupo de WhatsApp: create o each"}
    if mode != "mirror" and not text:
        return {"ok": False, "needs": "text", "error": "message_group necesita el texto (`text`)"}
    if mode == "group" and mirror is None:
        return {"ok": False, "needs": "mode", "error": "este grupo no tiene grupo de WhatsApp: create o each"}
    if mode in ("create", "mirror") and mirror is not None:
        mode = "group" if text else "mirror_exists"
    if mode == "mirror_exists":
        return {"ok": False, "error": f"ya hay un grupo de WhatsApp «{mirror.get('name')}»"}
    people = _d._groups.members(db, g)
    platform = "whatsapp" if mode in ("create", "mirror") else ""
    reach = [c for c in people if _reachable(c, platform)]
    left = [str(c.get("name") or c.get("id")) for c in people if c not in reach]
    if mode != "group" and not reach:
        return {"ok": False, "error": "nadie de este grupo tiene por dónde escribirle", "left_out": left}
    names = ", ".join(str(c.get("name") or c.get("id")) for c in reach)
    tpl = langs.words(f"contactos.order_{mode}", default="")
    if not tpl:
        return {"ok": False, "error": f"no hay frase para contactos.order_{mode} en el idioma del agente"}
    order = str(tpl).format(group=g.get("name"), names=names, text=text)
    why = _hand_over(order)
    if why:
        return {"ok": False, "reason": why, "error": "no hay ninguna conversación abierta: enciende el agente"
                if why == "no_session" else "el agente está parado"}
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"handed": order, "mode": mode, "left_out": left}})
    return d
