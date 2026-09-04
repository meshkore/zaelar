# Contacts widget — data layer (V2-541). ONE directory for every identity the operator keeps: people, places
# and companies (friends, restaurants, plumbers…), with freeform group labels, a city, favorites and
# parent/child links (the people you deal with AT a restaurant hang from it). This settles the question
# V2-523 left open, per the operator's direct order: a favourite place IS a directory entry with `favorite`
# as a flag — never a parallel per-kind list (the same day, a generated `restaurantes-favoritos-operador`
# widget was deleted at his request precisely so only this one exists).
#
# Reads/writes ONLY the widget's isolated store ("widgets/_data/contactos/state.json") — no coupling to the
# voice core. The record shape follows the V2-523 plan (kind person/place/company, parentId nesting, groupers)
# so the eventual memory/state integration is a projection, not a rewrite.
import re
import time
import unicodedata

from .. import store

WIDGET_ID = "contactos"

# Store schema version (lazy migration on read — see store.load). Bump when the shape changes.
DB_VERSION = 1


def _seed() -> dict:
    # Built fresh on every call: a module-level dict with a list inside is shallow-copied by dict() and a
    # later append would mutate the module seed (real shipped bug, V2-366).
    return {"contacts": [], "next_id": 1}


def _migrate(db: dict, from_v: int) -> dict:
    return db


def load_db() -> dict:
    if not store.exists(WIDGET_ID):
        store.save(WIDGET_ID, _seed())
    return store.load(WIDGET_ID, _seed(), version=DB_VERSION, migrate=_migrate)


def _norm(s) -> str:
    """Accent/case-insensitive comparable form, so «Elfo On» and «elfo ón» never pile up as duplicates."""
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


# The three structural kinds (V2-523: one identity set, not per-kind silos). A group label like «restaurantes»
# is NOT a kind — kinds say what the entry IS, groups say how the operator files it. Unknown values default to
# person rather than guessing from the label: inferring «place» from a group name would be exactly the kind of
# hardcoded world-knowledge this house forbids.
_KINDS = {"person": "person", "persona": "person", "people": "person",
          "place": "place", "lugar": "place", "sitio": "place",
          "company": "company", "empresa": "company", "negocio": "company", "business": "company"}


def _kind(v) -> str:
    return _KINDS.get(_norm(v), "person")


def _truthy(v, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    n = _norm(v)
    if n in ("true", "si", "sí", "yes", "1", "favorito", "favorita", "on"):
        return True
    if n in ("false", "no", "0", "off"):
        return False
    return default


def _groups_in(payload: dict) -> list[str]:
    """Group labels from a payload: `groups` (list or comma string) or `group` (one, possibly comma-separated).
    Trimmed, original casing kept, deduped by normalized form."""
    raw = payload.get("groups")
    if raw is None:
        raw = payload.get("group")
    if raw is None:
        return []
    parts = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    out, seen = [], set()
    for p in parts:
        p = re.sub(r"\s+", " ", str(p or "")).strip()
        if p and _norm(p) not in seen:
            seen.add(_norm(p))
            out.append(p)
    return out


# How long a pushed view stays worth OBEYING (same contract as the agenda's `show_day`, V2-540): the canvas
# re-renders only when the data's JSON signature changes and the widget re-applies only when the token moves,
# so `n` is a monotonic push counter; and freshness is decided HERE, where the clock is — a push kept forever
# would mean reopening the directory next week lands on last week's filter wearing the face of a deliberate one.
_VIEW_TTL_S = 600


def _fresh_view(db: dict) -> dict | None:
    v = db.get("view") or None
    if not v:
        return None
    at = float(v.get("at") or 0)
    return v if at and (time.time() - at) <= _VIEW_TTL_S else None


def _push_view(db: dict, sel: dict) -> None:
    db["view"] = {"sel": sel, "n": int((db.get("view") or {}).get("n", 0)) + 1, "at": time.time()}


def _group_matches(want: str, contact: dict) -> bool:
    """A spoken group matches a stored label loosely in BOTH directions («fontanero» ↔ «fontaneros»,
    «amigos» ↔ «amigos del trabajo») — containment over normalized forms, never a synonym table."""
    w = _norm(want)
    if not w:
        return True
    for g in contact.get("groups") or []:
        gn = _norm(g)
        if w in gn or gn in w:
            return True
    return False


def _matches(contacts: list, *, group: str = "", city: str = "", favorites=None, query: str = "") -> list:
    cw, qw = _norm(city), _norm(query)
    out = []
    for c in contacts:
        if group and not _group_matches(group, c):
            continue
        if cw:
            cn = _norm(c.get("city"))
            if not (cw in cn or (cn and cn in cw)):
                continue
        if favorites and not c.get("favorite"):
            continue
        if qw:
            hay = _norm(" ".join(str(c.get(k) or "") for k in ("name", "city", "address", "phone", "email", "notes"))
                        + " " + " ".join(c.get("groups") or []))
            if qw not in hay:
                continue
        out.append(c)
    # Favorites first, then by name — the answer to «¿cuál es mi favorito…?» should lead the list.
    out.sort(key=lambda c: (not c.get("favorite"), _norm(c.get("name"))))
    return out


def _public(c: dict) -> dict:
    """The compact row an action RESULT carries back to the brain — enough to answer by voice, never the
    whole record (the full data travels in view_data, and a result is read inside a prompt)."""
    out = {"id": c.get("id"), "name": c.get("name"), "kind": c.get("kind")}
    for k in ("city", "phone", "groups"):
        if c.get(k):
            out[k] = c[k]
    if c.get("favorite"):
        out["favorite"] = True
    return out


def view_data(q: str = "") -> dict:
    """Everything the render needs: the full archive (the widget filters client-side), the derived group rail,
    the cities present, and the pushed view (if fresh)."""
    db = load_db()
    contacts = db.get("contacts", [])
    groups: dict[str, dict] = {}
    cities: dict[str, str] = {}
    for c in contacts:
        for g in c.get("groups") or []:
            k = _norm(g)
            e = groups.setdefault(k, {"id": g, "count": 0})
            e["count"] += 1
        ct = str(c.get("city") or "").strip()
        if ct:
            cities.setdefault(_norm(ct), ct)
    return {
        "contacts": contacts,
        "groups": sorted(groups.values(), key=lambda g: (-g["count"], _norm(g["id"]))),
        "cities": sorted(cities.values(), key=_norm),
        "favorites_count": sum(1 for c in contacts if c.get("favorite")),
        "count": len(contacts),
        "view": _fresh_view(db),
    }


def prompt_digest() -> str:
    """What the directory ACTUALLY holds, compact enough to ride every turn prompt while the card is open
    (`refs.prompt_digest` contract; capped there, so this stays bounded on its own too).

    Why (V2-576, session 0a93de06 of 2026-09-04): asked «¿cuántos restaurantes favoritos tenemos?», the
    brain answered from stale memory pills («one») while the open card showed four — and when the operator
    pointed at the screen, it CONFABULATED a view explanation («la vista actual no lo muestra») for a
    mismatch it could not check. `ref_index` publishes labels without meaning: nothing said «these ARE all
    the favourites, four in total». The digest states the authoritative counts and rows, and says out loud
    that it outranks memory, so speech about this card starts from what the operator is looking at."""
    db = load_db()
    contacts = db.get("contacts", [])
    favs = sum(1 for c in contacts if c.get("favorite"))
    if not contacts:
        return ("Directorio VACÍO: 0 contactos, 0 favoritos. Si tu memoria dice otra cosa, MANDA este "
                "bloque: no afirmes que hay entradas guardadas.")
    lines = [f"Directorio COMPLETO y real: {len(contacts)} entradas, {favs} favoritas (⭐). Para contar o "
             "listar lo guardado, MANDA este bloque sobre tu memoria y sobre la conversación: lo que no "
             "esté aquí NO está guardado."]
    sel = ((_fresh_view(db) or {}).get("sel")) or {}
    if sel:
        bits = []
        if "favorites" in sel:
            bits.append("solo favoritos" if sel["favorites"] else "solo no-favoritos")
        bits += [f"{k}: {sel[k]}" for k in ("group", "city", "query") if sel.get(k)]
        if bits:
            lines.append("Vista filtrada en pantalla ahora: " + " · ".join(bits) + ".")
    for c in contacts[:15]:
        row = ("⭐ " if c.get("favorite") else "· ") + str(c.get("name") or c.get("id"))
        extra = [str(c.get("kind") or "")] if c.get("kind") not in (None, "", "person") else []
        extra += [str(c.get("city") or "")] if c.get("city") else []
        extra += [", ".join(c.get("groups") or [])] if c.get("groups") else []
        extra += [f"tel {c['phone']}"] if c.get("phone") else []
        if c.get("notes"):
            extra.append(str(c["notes"])[:80])
        if extra:
            row += " (" + "; ".join(x for x in extra if x) + ")"
        lines.append(row)
    if len(contacts) > 15:
        lines.append(f"… y {len(contacts) - 15} entradas más (la tarjeta las enseña todas).")
    return "\n".join(lines)


def ref_index() -> list[dict]:
    """Items the brain can reference by voice (V2-026): every contact, by name (+city to disambiguate two
    «Juan»s). `field` is the payload key every action uses, so refs resolve without the model guessing ids."""
    out = []
    for c in load_db().get("contacts", []):
        label = str(c.get("name") or c.get("id"))
        if c.get("city"):
            label += f" ({c['city']})"
        hint = ", ".join(c.get("groups") or []) or str(c.get("kind") or "")
        out.append({"id": c["id"], "label": label, "field": "contactId", "hint": hint})
    return out


def _find(db: dict, cid) -> dict | None:
    for c in db.get("contacts", []):
        if c.get("id") == cid:
            return c
    return None


_FIELDS = ("name", "city", "address", "phone", "email", "notes")


def apply_action(action: str, payload: dict | None = None) -> dict:
    """Widget actions. Every payload may carry `q` — the instance the canvas stamps into every click
    (V2-540: it is always `q`, never anything else); this widget is single-instance, so it is accepted and
    ignored, but a handler that crashed on it would break every button on the card."""
    payload = payload or {}
    q = str(payload.get("q") or "")
    db = load_db()
    contacts = db.setdefault("contacts", [])
    now = time.strftime("%Y-%m-%d")

    if action == "add_contact":
        name = re.sub(r"\s+", " ", str(payload.get("name") or "")).strip()
        if not name:
            # V2-473 — the write does not INVENT: a nameless row wearing the face of success is worse than an
            # error that teaches the retry shape.
            return {"ok": False,
                    "error": "no me ha llegado el nombre — vuelve a llamar a add_contact con `name` (y si los "
                             "tienes: kind person/place/company, group, city, phone), sin preguntarle nada al "
                             "operador si ya te los dijo"}
        city = str(payload.get("city") or "").strip()
        existing = next((c for c in contacts
                         if _norm(c.get("name")) == _norm(name) and _norm(c.get("city")) == _norm(city)), None)
        groups = _groups_in(payload)
        if existing:
            # Same name+city = the same identity said again: UPDATE instead of duplicating (the directory
            # sibling of the agenda's V2-208 dedup — a silent duplicate is how two half-truths accumulate).
            for k in _FIELDS:
                if payload.get(k):
                    existing[k] = str(payload[k]).strip()
            if payload.get("kind"):
                existing["kind"] = _kind(payload["kind"])
            for g in groups:
                if _norm(g) not in {_norm(x) for x in existing.get("groups") or []}:
                    existing.setdefault("groups", []).append(g)
            if payload.get("favorite") is not None:
                existing["favorite"] = _truthy(payload.get("favorite"))
            existing["updated"] = now
            c, updated = existing, True
        else:
            c = {"id": f"c{db.get('next_id', 1)}", "kind": _kind(payload.get("kind")),
                 "name": name, "city": city,
                 "address": str(payload.get("address") or "").strip(),
                 "phone": str(payload.get("phone") or "").strip(),
                 "email": str(payload.get("email") or "").strip(),
                 "notes": str(payload.get("notes") or "").strip(),
                 "groups": groups, "favorite": _truthy(payload.get("favorite")),
                 "parentId": "", "created": now, "updated": now}
            db["next_id"] = int(db.get("next_id", 1)) + 1
            contacts.append(c)
            updated = False
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": {"contact": _public(c), "updated": updated}})
        return d

    if action == "update_contact":
        c = _find(db, payload.get("contactId"))
        if not c:
            return {"ok": False,
                    "error": "no encuentro ese contacto — vuelve a llamar a update_contact con su `contactId` "
                             "(pásame el nombre en `item` y lo resuelvo yo)"}
        for k in _FIELDS:
            if payload.get(k) is not None and str(payload.get(k)).strip() != "":
                c[k] = str(payload[k]).strip()
        if payload.get("kind"):
            c["kind"] = _kind(payload["kind"])
        if payload.get("groups") is not None:
            c["groups"] = _groups_in({"groups": payload.get("groups")})
        elif payload.get("group"):
            for g in _groups_in({"group": payload.get("group")}):
                if _norm(g) not in {_norm(x) for x in c.get("groups") or []}:
                    c.setdefault("groups", []).append(g)
        if payload.get("favorite") is not None:
            c["favorite"] = _truthy(payload.get("favorite"))
        c["updated"] = now
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": {"contact": _public(c)}})
        return d

    if action == "remove_contact":
        c = _find(db, payload.get("contactId"))
        if not c:
            return {"ok": False, "error": "no encuentro ese contacto — remove_contact necesita su `contactId`"}
        db["contacts"] = [x for x in contacts if x.get("id") != c["id"]]
        for x in db["contacts"]:
            # Children never keep a pointer to a removed parent — a dangling link paints a dead breadcrumb.
            if x.get("parentId") == c["id"]:
                x["parentId"] = ""
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": {"removed": _public(c)}})
        return d

    if action == "set_favorite":
        c = _find(db, payload.get("contactId"))
        if not c:
            return {"ok": False, "error": "no encuentro ese contacto — set_favorite necesita su `contactId`"}
        c["favorite"] = _truthy(payload.get("favorite"), default=True)
        c["updated"] = now
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": {"contact": _public(c)}})
        return d

    if action == "link_contact":
        c = _find(db, payload.get("contactId"))
        if not c:
            return {"ok": False, "error": "no encuentro ese contacto — link_contact necesita su `contactId`"}
        pid = str(payload.get("parentId") or "").strip()
        if pid:
            parent = _find(db, pid)
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
                cur = _find(db, cur["parentId"])
        c["parentId"] = pid
        c["updated"] = now
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": {"contact": _public(c), "parentId": pid}})
        return d

    if action == "show_view":
        # THE VIEW IS AN ACTION (V2-540's lesson, applied at birth instead of after the incident): filtering
        # what is on screen has a NAME in the manifest, and the same call ANSWERS the query — the matches ride
        # in `result` so «¿cuál es mi restaurante favorito en Barcelona?» is one call, not a promise.
        sel = {}
        for k in ("group", "city", "query"):
            v = str(payload.get(k) or "").strip()
            if v:
                sel[k] = v
        fav = payload.get("favorites")
        if fav is not None and str(fav).strip() != "":
            sel["favorites"] = _truthy(fav)
        _push_view(db, sel)
        store.save(WIDGET_ID, db)
        found = _matches(contacts, group=sel.get("group", ""), city=sel.get("city", ""),
                         favorites=sel.get("favorites"), query=sel.get("query", ""))
        d = view_data(q)
        d.update({"ok": True, "result": {"count": len(found), "matches": [_public(c) for c in found[:12]]}})
        return d

    if action == "show_contact":
        c = _find(db, payload.get("contactId"))
        if not c:
            return {"ok": False, "error": "no encuentro ese contacto — show_contact necesita su `contactId`"}
        _push_view(db, {"contactId": c["id"]})
        store.save(WIDGET_ID, db)
        kids = [_public(x) for x in db.get("contacts", []) if x.get("parentId") == c["id"]]
        d = view_data(q)
        d.update({"ok": True, "result": {"contact": _public(c), "linked": kids}})
        return d

    return {"ok": False, "error": f"acción desconocida: {action}"}
