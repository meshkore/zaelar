"""The contacts card's VIEW and SYNC actions — show, sources, members, auto-sync (split from `actions.py`)."""
from __future__ import annotations

from . import data as _d


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


def _a_show_contact_members(action, payload, q, db, contacts, now) -> dict:
    c = _d._find(db, payload.get("contactId"))
    if not c or c.get("kind") != "group":
        return {"ok": False, "error": "eso no es un grupo — pide el grupo por su nombre"}
    rows = [_d._public(x) for x in _d.visible(db) if x["id"] in (c.get("members") or [])]
    _d._push_view(db, {"contactId": c["id"]})          # declared a view: the card opens the group it read out
    _d.store.save(_d.WIDGET_ID, db)
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
    if sel.get("kind"):
        sel["kind"] = _d._kind(sel["kind"])           # the card compares kinds literally («empresa» → company)
    fl = _d.model.flag(payload.get("flag") or "")
    if fl == "favorite":
        payload = {**payload, "favorites": True}
    elif fl:
        sel["flag"] = fl
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
                     kind=sel.get("kind", ""), source=sel.get("source", ""), flag_=sel.get("flag", ""))
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
    res = _d.gcontacts.sync(db, merge=_d.gmerge.merge_imported, remove=_d.gmerge.drop_deleted,
                         since=float((db.get("sync") or {}).get("last") or 0.0))
    if not res.get("ok"):
        return {"ok": False, "error": str(res.get("error") or "no se pudo sincronizar")}
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": res})
    return d
