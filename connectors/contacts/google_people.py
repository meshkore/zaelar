"""google_people.py — the People API, and the shape it becomes (V2-699).

One job: turn a Google `person` into the record `widgets/contactos/data.py` already stores, so the import
is a PROJECTION and not a second schema. Nothing here writes; nothing here knows about the widget.

⚠️ **Everything in a person is attacker-influenced.** Anybody who emails the operator can end up in
«Other contacts» with a display name they chose. So every string is trimmed and capped here, at the
boundary, rather than at each of the places that later render it — the card, the prompt digest and the
voice payloads read the same row and only one of them would have remembered.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.contacts.google")

#: What we ask Google for. Deliberately short: every extra field is personal data crossing a network and
#: landing in a local store for a card that would not show it.
PERSON_FIELDS = "names,emailAddresses,phoneNumbers,addresses,organizations,biographies,memberships"
OTHER_FIELDS = "names,emailAddresses,phoneNumbers"

#: Google's own system labels. `starred` is the one that MEANS something to us (it is his ★); the rest are
#: plumbing that would land in the sidebar as groups nobody chose.
_SYSTEM_GROUPS = {"myContacts", "all", "chatBuddies", "blocked"}
_STARRED = "starred"

_MAXLEN = {"name": 80, "email": 120, "phone": 40, "city": 60, "address": 200, "notes": 300, "group": 40}


def _cap(v, kind: str) -> str:
    return str(v or "").strip()[:_MAXLEN.get(kind, 120)]


def _primary(items, key: str = "value") -> str:
    """The row Google marked primary, else the first one that has a value. Google does not always mark
    one, and taking `[0]` blindly is how an old work address becomes somebody's only address."""
    rows = [r for r in (items or []) if isinstance(r, dict) and str(r.get(key) or "").strip()]
    if not rows:
        return ""
    for r in rows:
        if ((r.get("metadata") or {}).get("primary")):
            return str(r.get(key))
    return str(rows[0].get(key))


def _city_of(addresses) -> str:
    rows = [r for r in (addresses or []) if isinstance(r, dict)]
    for r in rows:
        if (r.get("metadata") or {}).get("primary") and str(r.get("city") or "").strip():
            return str(r["city"])
    for r in rows:
        if str(r.get("city") or "").strip():
            return str(r["city"])
    return ""


def person_to_contact(p: dict, group_names: dict | None = None) -> dict | None:
    """One Google person as OUR record, or None when there is not enough of it to be a contact.

    «Not enough» means no name AND no email: a row with only a phone number and no way to say who it is
    would land in the directory as a blank line the operator cannot act on or search for. Google's «Other
    contacts» are full of them.
    """
    if not isinstance(p, dict):
        return None
    group_names = group_names or {}
    name = _cap(_primary(p.get("names"), "displayName"), "name")
    email = _cap(_primary(p.get("emailAddresses")), "email")
    if not name and not email:
        return None
    if not name:
        name = _cap(email.split("@", 1)[0], "name")

    org = ""
    for o in (p.get("organizations") or []):
        if isinstance(o, dict) and str(o.get("name") or "").strip():
            org = _cap(o["name"], "name")
            break

    groups, favorite = [], False
    for m in (p.get("memberships") or []):
        if not isinstance(m, dict):
            continue
        gid = str(((m.get("contactGroupMembership") or {}).get("contactGroupId")) or "").strip()
        if not gid or gid in _SYSTEM_GROUPS:
            continue
        if gid == _STARRED:
            # His ★ in Google IS his ★ here. The directory's favourites are the same idea by the same
            # person, and importing them as a group called «starred» would have made him re-star everyone.
            favorite = True
            continue
        label = _cap(group_names.get(gid) or "", "group")
        if label and label not in groups:
            groups.append(label)

    out = {
        "name": name,
        "kind": "person",
        "email": email,
        "phone": _cap(_primary(p.get("phoneNumbers")), "phone"),
        "city": _cap(_city_of(p.get("addresses")), "city"),
        "address": _cap(_primary(p.get("addresses"), "formattedValue"), "address"),
        "notes": _cap(_primary(p.get("biographies")), "notes"),
        "groups": groups[:10],
        "favorite": favorite,
        "googleId": str(p.get("resourceName") or "").strip()[:80],
    }
    if org and org.lower() != name.lower():
        out["notes"] = (out["notes"] + " · " if out["notes"] else "") + org
        out["notes"] = _cap(out["notes"], "notes")
    return out


def _get(client, api_base: str, token: str, path: str, params: dict) -> dict:
    r = client.get(f"{api_base}{path}", params=params,
                   headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code >= 400:
        return {"ok": False, "status": r.status_code, "error": (r.text or "")[:300]}
    try:
        return {"ok": True, "body": r.json()}
    except Exception as e:
        return {"ok": False, "status": r.status_code, "error": f"respuesta ilegible: {e}"}


def contact_groups(client, api_base: str, token: str) -> dict:
    """`contactGroupId → its name`, so Google's labels become our group labels rather than opaque ids.

    Best effort: a failure here costs the LABELS, not the import, so it answers `{}` instead of raising —
    losing everyone's name because a secondary call 403'd would be the wrong trade.
    """
    res = _get(client, api_base, token, "/contactGroups", {"pageSize": 200})
    if not res.get("ok"):
        logger.info(f"contact groups unavailable ({res.get('status')}) — importing without labels")
        return {}
    out = {}
    for g in (res["body"].get("contactGroups") or []):
        if not isinstance(g, dict):
            continue
        gid = str(((g.get("resourceName") or "").rsplit("/", 1) or [""])[-1]).strip()
        nm = str(g.get("formattedName") or g.get("name") or "").strip()
        if gid and nm and gid not in _SYSTEM_GROUPS and gid != _STARRED:
            out[gid] = nm
    return out


def list_people(client, api_base: str, token: str, *, other: bool = False, max_pages: int = 20) -> dict:
    """Every connection (or every «other contact»), following `nextPageToken`.

    `max_pages` is a floor under a runaway loop, not a product limit: at 500 rows a page it is 10 000
    contacts, and a token that never stopped changing would otherwise pin the engine forever.
    """
    path, params = ("/otherContacts", {"readMask": OTHER_FIELDS, "pageSize": 200}) if other else \
                   ("/people/me/connections", {"personFields": PERSON_FIELDS, "pageSize": 500,
                                               "sortOrder": "LAST_MODIFIED_DESCENDING"})
    rows, token_page, pages = [], "", 0
    while pages < max_pages:
        q = dict(params)
        if token_page:
            q["pageToken"] = token_page
        res = _get(client, api_base, token, path, q)
        if not res.get("ok"):
            # A partial page already read is worth keeping: an import that reached 400 of 450 contacts and
            # then threw everything away because page 3 timed out helps nobody.
            return {"ok": False, "error": res.get("error") or "", "status": res.get("status"), "people": rows}
        body = res["body"]
        rows += [p for p in (body.get("otherContacts") if other else body.get("connections")) or []
                 if isinstance(p, dict)]
        token_page = str(body.get("nextPageToken") or "")
        pages += 1
        if not token_page:
            break
    return {"ok": True, "people": rows, "truncated": bool(token_page)}


# ── WRITING BACK (V2-699) ───────────────────────────────────────────────────────────────────────────────
# The operator asked for a link in both directions: «si se modifica algo en nuestro agente, un nombre, un
# teléfono, también se modifica en Google».
#
# ⚠️ Two traps, and both have already been paid for elsewhere in this engine:
#
#   1. **An update needs the person's current `etag`.** Google rejects a PATCH without it (409 / 400), and
#      that is a FEATURE: the etag is what stops us overwriting an edit somebody made on their phone since
#      we last read. So every update is a READ-MODIFY-WRITE — exactly the shape V2-697's calendar RSVP had
#      to become when a PATCH carrying an array silently replaced it.
#   2. **`updatePersonFields` is a whitelist, and anything listed is REPLACED.** A field we list but do not
#      send is CLEARED on Google's side. So we list exactly the fields we are sending, never a constant.

#: The fields we are ever willing to write. Anything outside this set is Google's and stays Google's.
WRITABLE = ("names", "emailAddresses", "phoneNumbers", "addresses", "biographies")


def contact_to_person(c: dict) -> dict:
    """Our record as the person body Google expects. Only the fields that carry a value — see trap 2."""
    body: dict = {}
    if str(c.get("name") or "").strip():
        body["names"] = [{"displayName": str(c["name"]).strip()}]
    if str(c.get("email") or "").strip():
        body["emailAddresses"] = [{"value": str(c["email"]).strip()}]
    if str(c.get("phone") or "").strip():
        body["phoneNumbers"] = [{"value": str(c["phone"]).strip()}]
    addr = str(c.get("address") or "").strip()
    city = str(c.get("city") or "").strip()
    if addr or city:
        row = {}
        if addr:
            row["formattedValue"] = addr
        if city:
            row["city"] = city
        body["addresses"] = [row]
    if str(c.get("notes") or "").strip():
        body["biographies"] = [{"value": str(c["notes"]).strip(), "contentType": "TEXT_PLAIN"}]
    return body


def get_person(client, api_base: str, token: str, resource_name: str) -> dict:
    rn = str(resource_name or "").strip().lstrip("/")
    if not rn.startswith("people/"):
        return {"ok": False, "error": "resourceName inválido"}
    return _get(client, api_base, token, f"/{rn}", {"personFields": PERSON_FIELDS})


def update_person(client, api_base: str, token: str, resource_name: str, contact: dict) -> dict:
    """Write our values onto an existing Google person, keeping everything we do not send."""
    live = get_person(client, api_base, token, resource_name)
    if not live.get("ok"):
        return {"ok": False, "error": live.get("error") or "", "status": live.get("status")}
    etag = str((live["body"] or {}).get("etag") or "")
    if not etag:
        return {"ok": False, "error": "Google no devolvió etag — no se puede escribir sin él"}
    body = contact_to_person(contact)
    if not body:
        return {"ok": True, "skipped": True}
    body["etag"] = etag
    fields = ",".join(k for k in WRITABLE if k in body)
    rn = str(resource_name).strip().lstrip("/")
    r = client.patch(f"{api_base}/{rn}:updateContact", params={"updatePersonFields": fields},
                     json=body, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code >= 400:
        return {"ok": False, "status": r.status_code, "error": (r.text or "")[:300]}
    try:
        return {"ok": True, "person": r.json()}
    except Exception:
        return {"ok": True, "person": {}}


def create_person(client, api_base: str, token: str, contact: dict) -> dict:
    body = contact_to_person(contact)
    if not body.get("names"):
        return {"ok": False, "error": "un contacto sin nombre no se crea en Google"}
    r = client.post(f"{api_base}/people:createContact", json=body,
                    headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code >= 400:
        return {"ok": False, "status": r.status_code, "error": (r.text or "")[:300]}
    try:
        return {"ok": True, "person": r.json()}
    except Exception:
        return {"ok": True, "person": {}}
