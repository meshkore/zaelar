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


#: How many phones / e-mails one person may bring. A directory entry is not a phone book of its own, and
#: the cap is what stops a pathological row (a shared mailbox with forty aliases) from riding into every
#: prompt this contact ever appears in.
_MAX_DETAILS = 6


def _all(items, kind: str, key: str = "value") -> list[dict]:
    """EVERY phone / e-mail Google holds for this person, primary first, each with the label Google gives it
    (`type`: mobile, work, home…) — V2-715, «varios teléfonos vinculados a la misma empresa». Before this,
    `_primary` was the whole import: a company with a switchboard, a mobile and a fax arrived as one number
    and the other two did not exist on this side."""
    rows = [r for r in (items or []) if isinstance(r, dict) and str(r.get(key) or "").strip()]
    rows.sort(key=lambda r: 0 if (r.get("metadata") or {}).get("primary") else 1)
    out, seen = [], set()
    for r in rows:
        value = _cap(r.get(key), kind)
        ident = value.lower()
        if not value or ident in seen:
            continue
        seen.add(ident)
        out.append({"value": value, "label": _cap(r.get("formattedType") or r.get("type"), "group")})
        if len(out) >= _MAX_DETAILS:
            break
    return out


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
        "phones": _all(p.get("phoneNumbers"), "phone"),
        "emails": _all(p.get("emailAddresses"), "email"),
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


def is_expired_sync_token(res: dict) -> bool:
    """Google refusing a sync token because it has aged out. Documented as a 429 carrying the reason
    `EXPIRED_SYNC_TOKEN`; older deployments answered 410. Both mean the same thing and the same remedy:
    throw the token away and read everything once."""
    st = res.get("status")
    body = str(res.get("error") or "")
    return st == 410 or (st == 429 and "EXPIRED_SYNC_TOKEN" in body) or "EXPIRED_SYNC_TOKEN" in body


def list_people(client, api_base: str, token: str, *, other: bool = False, max_pages: int = 20,
                sync_token: str = "") -> dict:
    """Every connection (or every «other contact»), following `nextPageToken` — or, with `sync_token`,
    only what has CHANGED since that token was issued.

    The incremental read is what makes a permanent sync affordable: an address book of 2 685 people is six
    pages every pass, and a minute-by-minute poll of six pages is a request budget nobody should spend to
    learn that nothing happened. With a token, a quiet minute is ONE round-trip that returns no people.

    ⚠️ Two rules of Google's, both load-bearing here:
      1. **`sortOrder` may not be combined with a sync request** — it is «only used if sync is not
         requested». So it is gone from BOTH regimes rather than only from the incremental one, because…
      2. …**«when the syncToken is specified, all other request parameters must match the first call»**.
         Two parameter sets that drift apart are a token Google will refuse, so there is exactly one.
    Ordering was never load-bearing for us: the merge matches on identity, not on arrival.

    Deleted people come back as a person carrying `metadata.deleted` and nothing else — no name, no email —
    so they are separated here into `deleted` instead of being handed to a shaper that would drop them.

    `max_pages` is a floor under a runaway loop, not a product limit: at 500 rows a page it is 10 000
    contacts, and a token that never stopped changing would otherwise pin the engine forever.
    """
    path, params = ("/otherContacts", {"readMask": OTHER_FIELDS, "pageSize": 200}) if other else \
                   ("/people/me/connections", {"personFields": PERSON_FIELDS, "pageSize": 500})
    params["requestSyncToken"] = "true"
    if sync_token:
        params["syncToken"] = sync_token
    rows, deleted, token_page, pages, next_sync = [], [], "", 0, ""
    while pages < max_pages:
        q = dict(params)
        if token_page:
            q["pageToken"] = token_page
        res = _get(client, api_base, token, path, q)
        if not res.get("ok"):
            # A partial page already read is worth keeping: an import that reached 400 of 450 contacts and
            # then threw everything away because page 3 timed out helps nobody.
            return {"ok": False, "error": res.get("error") or "", "status": res.get("status"),
                    "people": rows, "deleted": deleted, "expired": is_expired_sync_token(res)}
        body = res["body"]
        for p in (body.get("otherContacts") if other else body.get("connections")) or []:
            if not isinstance(p, dict):
                continue
            if (p.get("metadata") or {}).get("deleted"):
                gid = str(p.get("resourceName") or "").strip()[:80]
                if gid:
                    deleted.append(gid)
                continue
            rows.append(p)
        token_page = str(body.get("nextPageToken") or "")
        next_sync = str(body.get("nextSyncToken") or "") or next_sync
        pages += 1
        if not token_page:
            break
    return {"ok": True, "people": rows, "deleted": deleted, "truncated": bool(token_page),
            "syncToken": next_sync}


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
    # ALL of them, in our order, primary first — the same list the card edits (V2-715). Falls back to the
    # scalar for a row written before the lists existed, so a legacy contact still pushes its one number.
    for ours, theirs, kind in (("emails", "emailAddresses", "email"), ("phones", "phoneNumbers", "phone")):
        rows = [{"value": str(r.get("value")).strip(), **({"type": str(r.get("label")).strip()}
                                                          if str(r.get("label") or "").strip() else {})}
                for r in (c.get(ours) or [])
                if isinstance(r, dict) and str(r.get("value") or "").strip()]
        if not rows and str(c.get(kind) or "").strip():
            rows = [{"value": str(c[kind]).strip()}]
        if rows:
            body[theirs] = rows[:_MAX_DETAILS]
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


def delete_person(client, api_base: str, token: str, resource_name: str) -> dict:
    """Remove a person from Google (V2-701 — the other half of the mirror).

    The operator's model, in his own words: «es un espejo nuestro sistema, así como Google Contacts […] si
    eso está conectado a un teléfono y se modifica en el teléfono, todo el sistema se sincronizará». A
    mirror that reflects every change except a deletion is not a mirror: the row he removed here comes
    back on the next full re-read, and he has no way to tell why.

    A person Google no longer has answers 404, and that is SUCCESS for us: the end state he asked for is
    «it is not there», and it is not there.
    """
    rn = str(resource_name).strip().lstrip("/")
    if not rn:
        return {"ok": False, "error": "sin resourceName no se puede borrar en Google"}
    r = client.delete(f"{api_base}/{rn}:deleteContact",
                      headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code == 404:
        return {"ok": True, "already": True}
    if r.status_code >= 400:
        return {"ok": False, "status": r.status_code, "error": (r.text or "")[:300]}
    return {"ok": True}
