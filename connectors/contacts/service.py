"""service.py — read the address book, hand it over SHAPED (V2-699).

The boundary this file defends: the connector FETCHES, the widget MERGES. Nothing here touches
`widgets/_data/contactos/state.json`. That store belongs to the widget — it is the one place that knows
what the operator typed himself, and a connector reaching into it would be a second writer of a record
with no arbitration (`zaelar-modularity.md`; the same rule that keeps the calendar connector out of the
agenda's rows).

So the answer to «did it import?» is always a COUNT the widget produced, never one claimed from here.
"""
from __future__ import annotations

import logging

from . import google_people as _gp
from . import oauth as _oauth
from . import providers as _pv

logger = logging.getLogger("zaelar.contacts.service")


def connected(provider_id: str = "google-contacts") -> bool:
    return _oauth.tokens_present(provider_id)


# Google issues ONE sync token per list, and we read two of them («connections» and «other contacts»).
# They travel as a single opaque string so the widget stores one field and never has to know that.
_SEP = "\x1f"


def _split(token: str) -> dict:
    parts = str(token or "").split(_SEP)
    return {"main": parts[0] if parts else "", "other": parts[1] if len(parts) > 1 else ""}


def _join(tokens: dict) -> str:
    main, other = str(tokens.get("main") or ""), str(tokens.get("other") or "")
    # An incremental pass that came back WITHOUT a fresh token cannot be continued incrementally: saying so
    # (an empty string) costs one full re-read, while keeping the spent one costs a 429 on every pass.
    return (main + _SEP + other) if other else main


def fetch(provider_id: str = "google-contacts", *, sync_token: str = "") -> dict:
    """Every contact the connected account will give us, already in our record shape — or, with
    `sync_token`, only what CHANGED since that token was issued.

    The caller gets back a fresh `syncToken` to keep, a `deleted` list of resource names Google no longer
    has, and `full`: whether this read saw the whole address book or only a delta. That last flag is not
    bookkeeping — a merge is allowed to trust a delta row («Google changed this since we last looked») in
    ways it must never trust a row from a full re-read, where «changed» is unknown.

    An expired token is not an error the operator should ever see: it is retried ONCE as a full read, which
    is exactly the remedy Google documents for it.

    Never raises: every door in this engine answers `{"ok": False, "error": …}` so a dormant or broken
    connector degrades into a sentence the operator can act on, not a traceback in a log he never opens.
    """
    p = _pv.get(provider_id)
    if not p:
        return {"ok": False, "error": f"proveedor desconocido: {provider_id}"}
    if not _oauth.configured(p.id):
        return {"ok": False, "error": "todavía no hay una app de Google registrada — conéctala en la "
                                      "pestaña de Conectores"}
    tok = _oauth.access_token(p.id)
    if not tok:
        return {"ok": False, "error": "no hay conexión con Google Contacts — pulsa «Conectar» en la "
                                      "pestaña de Conectores y autoriza el acceso a tus contactos"}
    tier = p.tier(_oauth.account(p.id).get("tier") or "")
    want_other = "contacts.other.readonly" in " ".join(tier.scopes)

    try:
        import httpx
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"sin cliente HTTP: {e}"}

    shaped: list[dict] = []
    seen: set[str] = set()
    deleted: list[str] = []
    truncated = False
    tokens: dict[str, str] = {}
    full = not sync_token
    with httpx.Client() as client:
        res = _gp.list_people(client, p.api_base, tok, sync_token=_split(sync_token).get("main", ""))
        if res.get("expired"):
            # Documented remedy, and the only one: drop the token and read everything once.
            logger.info("contacts sync token expired — falling back to a full read")
            full = True
            res = _gp.list_people(client, p.api_base, tok)
        if not res.get("ok") and not res.get("people"):
            st = res.get("status")
            if st in (401, 403):
                return {"ok": False, "error": "Google ha rechazado el acceso a tus contactos. Vuelve a "
                                              "conectar la cuenta y acepta el permiso de contactos."}
            return {"ok": False, "error": f"Google no ha contestado bien ({st}): {res.get('error') or ''}"[:300]}
        truncated = bool(res.get("truncated"))
        deleted += list(res.get("deleted") or [])
        tokens["main"] = str(res.get("syncToken") or "")
        # The labels cost a request of their own, and a quiet incremental pass has nobody to label. Asking
        # for them anyway would double the steady-state cost of a permanent sync to learn nothing.
        groups = _gp.contact_groups(client, p.api_base, tok) if res.get("people") else {}
        batches = [(res.get("people") or [], groups)]
        if want_other:
            if not _split(sync_token).get("other"):
                full = True          # one half read in full makes the whole pass a full read, not a delta
            other = _gp.list_people(client, p.api_base, tok, other=True,
                                    sync_token=_split(sync_token).get("other", ""))
            if other.get("expired"):
                full = True
                other = _gp.list_people(client, p.api_base, tok, other=True)
            # «Other contacts» carry no memberships, so they get no labels — and a failure here never
            # costs the real address book that already came back above.
            batches.append((other.get("people") or [], {}))
            truncated = truncated or bool(other.get("truncated"))
            deleted += list(other.get("deleted") or [])
            tokens["other"] = str(other.get("syncToken") or "")

    for rows, gnames in batches:
        for raw in rows:
            c = _gp.person_to_contact(raw, gnames)
            if not c:
                continue
            # Google itself can return the same person twice across pages when the address book changes
            # mid-read. Dedup on the resource name first, then on name+email.
            key = c.get("googleId") or (c["name"].lower() + "|" + (c.get("email") or "").lower())
            if key in seen:
                continue
            seen.add(key)
            shaped.append(c)

    return {"ok": True, "contacts": shaped, "total": len(shaped), "truncated": truncated,
            "tier": tier.id, "included_other": want_other, "full": full,
            "deleted": deleted, "syncToken": _join(tokens)}


def can_write(provider_id: str = "google-contacts") -> bool:
    """Whether the tier the operator actually GRANTED can push back. Not what the registry offers — what
    he consented to, which is the only thing Google will honour."""
    return _pv.writes(provider_id, _oauth.account(provider_id).get("tier") or "")


def push(rows: list[dict], provider_id: str = "google-contacts", *, gone: list[str] | None = None) -> dict:
    """Send our side of the changes to Google. `rows` are OUR records; each carries `googleId` or not,
    and `gone` are resource names the operator removed HERE and Google must stop holding (V2-701).

    Never raises, and never reports more than it did: every row is counted as `sent`, `created` or
    `failed` individually, because a partial push is the normal case (one etag conflict must not throw
    away the other forty writes) and because «synced» is a claim the operator will trust.
    """
    p = _pv.get(provider_id)
    if not p:
        return {"ok": False, "error": f"proveedor desconocido: {provider_id}"}
    if not can_write(provider_id):
        return {"ok": False, "error": "la conexión con Google es de solo lectura — vuelve a conectarla "
                                      "eligiendo «Sincronización en los dos sentidos»"}
    tok = _oauth.access_token(p.id)
    if not tok:
        return {"ok": False, "error": "no hay conexión con Google Contacts"}
    try:
        import httpx
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"sin cliente HTTP: {e}"}

    sent = created = failed = removed = 0
    problems: list[str] = []
    with httpx.Client() as client:
        for gid in gone or []:
            res = _gp.delete_person(client, p.api_base, tok, str(gid))
            if res.get("ok"):
                removed += 1
            else:
                failed += 1
                if len(problems) < 3:
                    problems.append(f"borrar {gid}: {res.get('error') or res.get('status')}")
        for c in rows or []:
            gid = str(c.get("googleId") or "").strip()
            res = _gp.update_person(client, p.api_base, tok, gid, c) if gid \
                else _gp.create_person(client, p.api_base, tok, c)
            if res.get("ok"):
                if res.get("skipped"):
                    continue
                if gid:
                    sent += 1
                else:
                    created += 1
                    c["googleId"] = str((res.get("person") or {}).get("resourceName") or "")
            else:
                failed += 1
                if len(problems) < 3:
                    problems.append(f"{c.get('name') or c.get('id')}: {res.get('error') or res.get('status')}")
    return {"ok": True, "sent": sent, "created": created, "failed": failed, "removed": removed,
            "problems": problems}
