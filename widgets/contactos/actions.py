"""What each contacts action does, one function per action; `data.ACTIONS` maps the names to them (V2-778
F1-12, 2026-10-01).

Moved out of `widgets/contactos/data.py`'s `apply_action` if-chain with no behaviour change: each body is the branch
it was, and every module-level name of `data` it reads is read through it (`_d.<name>`), so a patch on `data`
still governs every call.
"""
from __future__ import annotations

from . import data as _d


def _a_add_contact(action, payload, q, db, contacts, now) -> dict:
    name = _d.re.sub(r"\s+", " ", str(payload.get("name") or "")).strip()
    if not name:
        # V2-473 — the write does not INVENT: a nameless row wearing the face of success is worse than an
        # error that teaches the retry shape.
        return {"ok": False,
                "error": "no me ha llegado el nombre — vuelve a llamar a add_contact con `name` (y si los "
                         "tienes: kind person/place/company, group, city, phone), sin preguntarle nada al "
                         "operador si ya te los dijo"}
    if _d._norm(payload.get("channel")) == "email" and not payload.get("email") and payload.get("value"):
        payload = {**payload, "email": payload.get("value")}   # demo pass 104: `{channel: email, value}`
    city = str(payload.get("city") or "").strip()
    groups = _d._groups_in(payload)
    incoming = _d._channels_in(payload)
    # Name+city first (the operator saying the same person again), then the ACCOUNT — one Telegram
    # username can only belong to one contact, whatever it is called this time (V2-693).
    existing = next((c for c in contacts
                     if _d._norm(c.get("name")) == _d._norm(name) and _d._norm(c.get("city")) == _d._norm(city)), None)
    if existing is None and incoming:
        existing = _d._owner_of_channel(contacts, incoming)
    if existing:
        # Same name+city = the same identity said again: UPDATE instead of duplicating (the directory
        # sibling of the agenda's V2-208 dedup — a silent duplicate is how two half-truths accumulate).
        for k in _d._FIELDS:
            if payload.get(k):
                existing[k] = str(payload[k]).strip()
        if payload.get("kind"):
            existing["kind"] = _d._kind(payload["kind"])
        for g in groups:
            if _d._norm(g) not in {_d._norm(x) for x in existing.get("groups") or []}:
                existing.setdefault("groups", []).append(g)
        if payload.get("favorite") is not None:
            existing["favorite"] = _d._truthy(payload.get("favorite"))
        for row in incoming:
            _d._merge_channel(existing, row)
        for key in ("phones", "emails"):
            for row in _d.model.details_in(payload, key) or []:
                _d.model.add_detail(existing, key, row["value"], row.get("label") or "")
        if _d._platform(payload.get("preferred")):
            existing["preferred"] = _d._platform(payload.get("preferred"))
        _d.model.normalize(existing)
        _d._touch(existing, now)
        c, updated = existing, True
    else:
        c = {"id": f"c{db.get('next_id', 1)}", "kind": _d._kind(payload.get("kind")),
             "name": name, "city": city,
             "address": str(payload.get("address") or "").strip(),
             "phone": str(payload.get("phone") or "").strip(),
             "email": str(payload.get("email") or "").strip(),
             "notes": str(payload.get("notes") or "").strip(),
             "groups": groups, "favorite": _d._truthy(payload.get("favorite")),
             "channels": incoming, "preferred": _d._platform(payload.get("preferred")),
             "phones": _d.model.details_in(payload, "phones") or [],
             "emails": _d.model.details_in(payload, "emails") or [],
             "parentId": "", "created": now, "updated": now, "touchedAt": _d.time.time()}
        _d.model.normalize(c)
        db["next_id"] = int(db.get("next_id", 1)) + 1
        contacts.append(c)
        updated = False
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"contact": _d._public(c), "updated": updated}})
    return d


def _a_update_contact(action, payload, q, db, contacts, now) -> dict:
    c = _d._find(db, payload.get("contactId"))
    if not c:
        return {"ok": False,
                "error": "no encuentro ese contacto — vuelve a llamar a update_contact con su `contactId` "
                         "(pásame el nombre en `item` y lo resuelvo yo)"}
    for k in _d._FIELDS:
        if payload.get(k) is not None and str(payload.get(k)).strip() != "":
            c[k] = str(payload[k]).strip()
    # V2-699 — EMPTYING a field is its own gesture, and it has to be, because the loop above ignores ""
    # on purpose: a model that omits a field, or sends it blank because it did not hear it, must never
    # wipe what the operator typed. The card is a deliberate hand on a deliberate field, so it names the
    # field it is clearing instead of relying on an empty string nobody can tell from an accident.
    for k in _d._clear_in(payload):
        if k in _d._FIELDS and k != "name":   # a nameless contact cannot be found again by voice or by eye
            c[k] = ""
            # …and the LIST goes with it. `normalize` keeps the scalar in step with the head of its
            # list, so emptying only the scalar would have the next read put the number straight back.
            if k in ("phone", "email"):
                c[k + "s"] = []
    if payload.get("kind"):
        c["kind"] = _d._kind(payload["kind"])
    if payload.get("groups") is not None:
        c["groups"] = _d._groups_in({"groups": payload.get("groups")})
    elif payload.get("group"):
        for g in _d._groups_in({"group": payload.get("group")}):
            if _d._norm(g) not in {_d._norm(x) for x in c.get("groups") or []}:
                c.setdefault("groups", []).append(g)
    if payload.get("favorite") is not None:
        c["favorite"] = _d._truthy(payload.get("favorite"))
    for row in _d._channels_in(payload):
        _d._merge_channel(c, row)
    # `phones`/`emails` REPLACE the list (that is what the card's ✕ and its editor send); `add_phone`
    # and `add_email` are the other half, for a sentence that only names one more number.
    for key in ("phones", "emails"):
        rows = _d.model.details_in(payload, key)
        if rows is not None:
            c[key] = rows
            c[_d.model._DETAIL_KEYS[key]] = rows[0]["value"] if rows else ""
    if _d._platform(payload.get("preferred")):
        c["preferred"] = _d._platform(payload.get("preferred"))
    _d.model.normalize(c)
    _d._touch(c, now)
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"contact": _d._public(c)}})
    return d


def _a_set_channel(action, payload, q, db, contacts, now) -> dict:
    # V2-683 — «a Iván escríbele por Telegram». The CHANNEL and the PREFERENCE are one gesture because
    # that is how it is said; `preferred` alone (no handle) just moves the preference to a channel that
    # already exists, which is the other half of the same sentence («mejor por WhatsApp»).
    c = _d._find(db, payload.get("contactId"))
    if not c:
        return {"ok": False, "error": "no encuentro ese contacto — set_channel necesita su `contactId` "
                                      "(pásame el nombre en `item` y lo resuelvo yo)"}
    p = _d._platform(payload.get("platform"))
    if not p:
        return {"ok": False, "error": "no me ha llegado la plataforma — set_channel necesita `platform` "
                                      "(whatsapp, telegram o email)"}
    handle = str(payload.get("handle") or payload.get("address") or "").strip()
    chat_id = str(payload.get("chatId") or "").strip()
    if _d._truthy(payload.get("remove")):
        # V2-699 — the card's ✕. It drops the PREFERENCE with the channel: a preferred platform the
        # contact no longer has is a promise the sending door cannot keep, and `channel_for` would fall
        # back silently to a different one, which is the same wrong-recipient family `refs.py` guards.
        c["channels"] = [ch for ch in (c.get("channels") or []) if str(ch.get("platform")) != p]
        if str(c.get("preferred") or "") == p:
            c["preferred"] = ""
        _d._touch(c, now)
        _d.store.save(_d.WIDGET_ID, db)
        d = _d.view_data(q)
        d.update({"ok": True, "result": {"contact": _d._public(c), "removed_channel": p}})
        return d
    # A handle that is only his NAME with an «@» in front is the model filling a required-looking slot,
    # not a handle anybody told it (INIT of the demo pass, 2026-09-28: «use his Telegram» came as
    # `handle: "@Rowan"` over Rowan's real `@rowan_example`, and would have overwritten it). Over a channel
    # we already have, it is dropped and the call only moves the preference, which is what was asked.
    _has_p = any(ch.get("platform") == p for ch in c.get("channels") or [])
    if handle and _has_p and _d._norm(handle.lstrip("@")) in {_d._norm(c.get("name") or ""),
                                                           _d._norm(str(c.get("name") or "").split(" ")[0])}:
        handle = ""
    if handle or chat_id:
        _d._merge_channel(c, {"platform": p, "handle": handle, "chatId": chat_id,
                           "source": "operator", "volume": 0, "last_seen": 0.0})
    elif not any(ch.get("platform") == p for ch in c.get("channels") or []):
        # Making a channel PREFERRED without saying how to reach it, when we do not know either, would
        # store a preference that no send can honour — and it would read as «done» to him.
        return {"ok": False,
                "error": f"no tengo ningún {p} suyo — vuelve a llamar a set_channel con `handle` "
                         f"(su usuario, su teléfono o su dirección)"}
    if _d._truthy(payload.get("preferred"), default=True):
        c["preferred"] = p
    _d._touch(c, now)
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"contact": _d._public(c), "channel": p}})
    return d


def _a_add_channel(action, payload, q, db, contacts, now) -> dict:
    # V2-715 — «varios teléfonos que estén vinculados a la misma empresa». One action per kind of
    # detail, both directions in one gesture (`remove: true`), the shape `set_channel` already uses:
    # a second action whose only job is to undo the first is a second thing to remember.
    key = "phones" if action == "add_phone" else "emails"
    field = "phone" if action == "add_phone" else "email"
    # Demo pass 102: «Rowan's Telegram is @rowan_example» came as `add_phone {channel: telegram, handle: @…}`
    # — a messaging handle with no number is his CHANNEL, never a phone.
    _plat = _d._platform(payload.get("platform") or payload.get("channel"))
    if action == "add_phone" and _plat in ("telegram", "whatsapp") and not str(payload.get("phone") or "").strip():
        return _a_set_channel("set_channel", {**payload, "platform": _plat}, q, db, contacts, now)
    c = _d._find(db, payload.get("contactId"))
    if not c:
        return {"ok": False, "error": f"no encuentro ese contacto — {action} necesita su `contactId` "
                                      "(pásame el nombre en `item` y lo resuelvo yo)"}
    value = str(payload.get(field) or payload.get("value") or payload.get("handle") or "").strip()
    if not value:
        return {"ok": False,
                "error": f"no me ha llegado el dato — vuelve a llamar a {action} con `{field}` "
                         f"(y `label` si te dijo de qué es: «centralita», «móvil»…)"}
    if _d._truthy(payload.get("remove")):
        changed = _d.model.drop_detail(c, key, value)
    else:
        changed = _d.model.add_detail(c, key, value, str(payload.get("label") or "").strip())
    if changed:
        _d._touch(c, now)
        _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"contact": _d._public(c), field + "s": _d.model.values(c, key),
                                     "changed": changed}})
    return d


def _a_show_sources(action, payload, q, db, contacts, now) -> dict:
    # The plug button, by voice (V2-715). Every control on this card has to be reachable both ways —
    # «ábreme los conectores de contactos» used to have no action at all, so the model's only move was
    # to show the widget and describe a button the operator was already looking at.
    _d._push_view(db, {"screen": "sources"})
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"screen": "sources",
                                     "sources": [{"id": p_["id"], "label": p_.get("label"),
                                                  "status": p_.get("status")}
                                                 for p_ in (d.get("providers") or [])]}})
    return d


def _a_remove_contact(action, payload, q, db, contacts, now) -> dict:
    c = _d._find(db, payload.get("contactId"))
    if not c:
        return {"ok": False, "error": "no encuentro ese contacto — remove_contact necesita su `contactId`"}
    db["contacts"] = [x for x in contacts if x.get("id") != c["id"]]
    for x in db["contacts"]:
        # Children never keep a pointer to a removed parent — a dangling link paints a dead breadcrumb.
        if x.get("parentId") == c["id"]:
            x["parentId"] = ""
        # …and neither does a GROUP keep a member who is gone (V2-714): the same rule, one relation
        # over. A stale id would paint a member count nobody can open.
        if c["id"] in (x.get("members") or []):
            x["members"] = [m for m in x["members"] if m != c["id"]]
    # V2-701 — the other half of the mirror. His model: «se modifica en un sitio o en otro, todo se
    # sincroniza linealmente y es un espejo». A deletion is a change like any other, and it is the one
    # a pull CANNOT carry: once the row is gone from here there is nothing left to compare, so the
    # intention is written down now and spent by the next push. Queued even when the connection is
    # read-only — the write permission may arrive before he next opens this card, and then it lands.
    gid = str(c.get("googleId") or "").strip()
    if gid:
        pend = db.setdefault("sync", {}).setdefault("pendingDeletes", [])
        if gid not in pend:
            pend.append(gid)
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"removed": _d._public(c)}})
    return d


def _a_set_favorite(action, payload, q, db, contacts, now) -> dict:
    c = _d._find(db, payload.get("contactId"))
    if not c:
        return {"ok": False, "error": "no encuentro ese contacto — set_favorite necesita su `contactId`"}
    c["favorite"] = _d._truthy(payload.get("favorite"), default=True)
    _d._touch(c, now)
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"contact": _d._public(c)}})
    return d


def _a_hide_contact(action, payload, q, db, contacts, now) -> dict:
    # HIDE, not delete (V2-714). «En local los contactos son editables y se pueden ocultar, se quedan
    # mapeados a las plataformas.» The mapping is the point: a hidden row still matches on the next
    # import, so the person he took off his screen does not come back every pass. Deleting still
    # exists and is still LOCAL — no platform here has an address-book write API.
    c = _d._find(db, payload.get("contactId"))
    if not c:
        return {"ok": False, "error": "no encuentro ese contacto — hide_contact necesita su `contactId`"}
    c["hidden"] = _d._truthy(payload.get("hidden"), default=True)
    _d._touch(c, now)
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"contact": _d._public(c), "hidden": c["hidden"]}})
    return d


def _a_sync_source(action, payload, q, db, contacts, now) -> dict:
    # ONE pass of ONE source, on demand. The permanent half is `sources.tick`; this is «trae mis
    # contactos de Telegram ahora».
    from . import sources
    res = sources.sync_now(str(payload.get("source") or "").strip().lower())
    if not res.get("ok"):
        return {**_d.view_data(q), **res}
    d = _d.view_data(q)
    d.update({"ok": True, "result": res})
    return d


def _a_link_contact(action, payload, q, db, contacts, now) -> dict:
    c = _d._find(db, payload.get("contactId"))
    if not c:
        return {"ok": False, "error": "no encuentro ese contacto — link_contact necesita su `contactId`"}
    pid = str(payload.get("parentId") or "").strip()
    if pid:
        parent = _d._find(db, pid)
        if not parent:
            return {"ok": False, "error": "no encuentro el contacto padre — link_contact necesita su `parentId`"}
        if pid == c["id"]:
            return {"ok": False, "error": "un contacto no puede colgar de sí mismo"}
        # Cycle guard: walking up from the parent must never reach the child being linked.
        seen, cur = set(), parent
        while cur is not None and cur.get("parentId"):
            if cur["parentId"] == c["id"] or cur["parentId"] in seen:
                return {"ok": False, "error": "ese enlace crearía un ciclo — deshaz antes el enlace contrario"}
            seen.add(cur["parentId"])
            cur = _d._find(db, cur["parentId"])
    c["parentId"] = pid
    _d._touch(c, now)
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"contact": _d._public(c), "parentId": pid}})
    return d


def _a_show_contact_members(action, payload, q, db, contacts, now) -> dict:
    c = _d._find(db, payload.get("contactId"))
    if not c or c.get("kind") != "group":
        return {"ok": False, "error": "eso no es un grupo — pide el grupo por su nombre"}
    rows = [_d._public(x) for x in _d.visible(db) if x["id"] in (c.get("members") or [])]
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"group": _d._public(c), "members": rows,
                                     "membersKnown": c.get("membersKnown", True)}})
    return d


def _a_show_view(action, payload, q, db, contacts, now) -> dict:
    # THE VIEW IS AN ACTION (V2-540's lesson, applied at birth instead of after the incident): filtering
    # what is on screen has a NAME in the manifest, and the same call ANSWERS the query — the matches ride
    # in `result` so «¿cuál es mi restaurante favorito en Barcelona?» is one call, not a promise.
    sel = {}
    for k in ("group", "city", "query", "kind", "source"):
        v = str(payload.get(k) or "").strip()
        if v:
            sel[k] = v
    fav = payload.get("favorites")
    if fav is not None and str(fav).strip() != "":
        sel["favorites"] = _d._truthy(fav)
    # The HIDDEN shelf, by voice (V2-715). It is the one rail section that reads a different pool, and
    # without this «enséñame los que oculté» had no answer at all — which is what makes hiding feel
    # like a delete with a softer word.
    hid = _d._truthy(payload.get("hidden"))
    if hid:
        sel["hidden"] = True
    pool = [c for c in (db.get("contacts") or []) if c.get("hidden")] if hid else _d.visible(db)
    _d._push_view(db, sel)
    _d.store.save(_d.WIDGET_ID, db)
    found = _d._matches(pool, group=sel.get("group", ""), city=sel.get("city", ""),
                     favorites=sel.get("favorites"), query=sel.get("query", ""),
                     kind=sel.get("kind", ""), source=sel.get("source", ""))
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"count": len(found), "matches": [_d._public(c) for c in found[:12]],
                                     **({"hidden": True} if hid else {})}})
    return d


def _a_show_contact(action, payload, q, db, contacts, now) -> dict:
    c = _d._find(db, payload.get("contactId"))
    if not c:
        return {"ok": False, "error": "no encuentro ese contacto — show_contact necesita su `contactId`"}
    _d._push_view(db, {"contactId": c["id"]})
    _d.store.save(_d.WIDGET_ID, db)
    kids = [_d._public(x) for x in db.get("contacts", []) if x.get("parentId") == c["id"]]
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"contact": _d._public(c), "linked": kids}})
    return d


def _a_set_auto(action, payload, q, db, contacts, now) -> dict:
    # V2-701 — «eso debería quedarse conectado de forma permanente». The switch is the state; the
    # background tick reads it every pass, so turning it off stops the next one with nothing to cancel.
    on = _d._truthy(payload.get("auto"), default=True)
    # V2-714 — ONE switch per source, and the same switch for both halves of it: «no vamos a poner dos
    # opciones… un botón de sincronizar que se queda activado». Naming a source routes to that source;
    # naming none keeps meaning Google, which is what every existing caller means.
    src = str(payload.get("source") or "").strip().lower()
    if src:
        from . import sources as _src
        res = _src.set_auto(src, on)
        d = _d.view_data(q)
        d.update({"ok": bool(res.get("ok")), "result": res} if res.get("ok") else res)
        return d
    db.setdefault("sync", {})["auto"] = on
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"auto": on}})
    return d


def _a_sync_contacts(action, payload, q, db, contacts, now) -> dict:
    # `import_google` is kept as an alias: it shipped in the manifest for one build and a model that
    # learned it must not start getting «acción desconocida» for asking the same thing.
    res = _d.gcontacts.sync(db, merge=_d.gcontacts.merge_imported, remove=_d.gcontacts.drop_deleted,
                         since=float((db.get("sync") or {}).get("last") or 0.0))
    if not res.get("ok"):
        return {"ok": False, "error": str(res.get("error") or "no se pudo sincronizar")}
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": res})
    return d
