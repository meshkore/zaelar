"""gcontacts.py — the Google Contacts GLUE between `widgets/contactos/data.py` and
`connectors/contacts/service.py` (V2-699).

Extracted for the same reason `widgets/agenda/gcal.py` was: `data.py` must stay stdlib-only at module
scope, and a widget's data layer that grows a connector inside it is the file nobody can read later.
Nothing here imports `data` at module scope — only lazily, inside the functions that need it.

## Who wins a conflict, and why the answer is `updated`

The operator asked for a link in both directions («si se modifica algo en nuestro agente, un nombre, un
teléfono, también se modifica en Google»). That makes «who wins» a question every pass has to answer, and
the answer is **whoever touched the row last**:

  · a row whose local `updated` is NEWER than the last completed sync is ours → it gets PUSHED;
  · anything else is Google's → its empty-or-differing fields get PULLED.

Not «he always wins», which is what a one-way import quietly asserts, and not «Google always wins», which
would undo his corrections. `updated` has recorded this since V2-541; the sync just started reading it.
"""
from __future__ import annotations

import time as _time

from loguru import logger

# CONTACT SOURCES shown in the widget's subheader (the agenda's V2-679 pattern, and its exact contract:
# a READ of the real inventory, never a hardcoded «off» — the day a second one is registered under this
# family it lights up here with nothing else to change).
#
# WHY THESE THREE: Google is the address book most people already have; iCloud is the other one anybody
# carries, reachable over CardDAV with an app-specific password; and a generic CardDAV covers
# Outlook/Fastmail/Nextcloud with one connector instead of three brands. Per INI-027, showing what we do
# NOT have is the point rather than an embarrassment.
_SOURCES = (("google-contacts", "Google Contacts"), ("icloud", "iCloud (Apple)"),
            ("carddav", "CardDAV (Outlook, Fastmail…)"))


def providers() -> list[dict]:
    """Connection state of each contact source, for the subheader strip.

    `status`: "connected" | "off" (built, not linked) | "unconfigured" (built, no OAuth client registered
    yet) | "unavailable" (no connector exists at all). The widget must be able to tell these apart —
    «you have not linked it» and «we have not built it» are different sentences, and showing the first
    when the second is true is the same class of lie as promising a view.
    """
    live: dict[str, dict] = {}
    try:
        from connectors import registry
        for d in registry.descriptors():
            if str(d.get("family") or "") == "contactos":
                live[str(d.get("id") or "")] = d
    except Exception:
        pass                                     # a registry that cannot be read is not a linked source
    known = dict(_SOURCES)
    out = [{"id": cid, "label": (live.get(cid, {}).get("label") or label),
            "status": ("connected" if live[cid].get("connected") else str(live[cid].get("status") or "off"))
                      if cid in live else "unavailable"}
           for cid, label in _SOURCES]
    out += [{"id": cid, "label": str(d.get("label") or cid),
             "status": "connected" if d.get("connected") else str(d.get("status") or "off")}
            for cid, d in live.items() if cid not in known]
    return out


def svc():
    """Lazy import of the contacts connector facade. None when it cannot even be imported — every caller
    here degrades to local-only behaviour when that happens."""
    try:
        from connectors.contacts import service as _s
        return _s
    except Exception as e:  # noqa: BLE001
        logger.debug(f"contacts connector unavailable: {e}")
        return None


def _oauth():
    try:
        from connectors.contacts import oauth as _o
        return _o
    except Exception:
        return None


def sync_state(db: dict) -> dict:
    """What the sync box paints. Derived per read — a cached «connected» is how a revoked token keeps
    wearing a green dot."""
    s = db.get("sync") or {}
    o, sv = _oauth(), svc()
    connected = bool(o and o.tokens_present("google-contacts"))
    return {
        "connected": connected,
        "twoWay": bool(sv and connected and sv.can_write("google-contacts")),
        "tier": (o.account("google-contacts").get("tier") if o and connected else "") or "",
        "last": float(s.get("last") or 0.0),
        "lastResult": s.get("lastResult") or {},
        "auto": bool(s.get("auto", True)),
    }


def connect(tier_id: str = "", origin: str = "") -> dict:
    """The consent URL. The operator's click opens it — the popup only survives inside the gesture that
    opened it, which is why `widget.js` opens the window synchronously and fills its `location` after."""
    o = _oauth()
    if not o:
        return {"ok": False, "error": "el conector de contactos no está disponible"}
    return o.authorize_url("google-contacts", tier_id, origin)


def disconnect() -> dict:
    o = _oauth()
    return o.forget("google-contacts") if o else {"ok": False, "error": "el conector no está disponible"}


def sync(db: dict, *, merge, since: float = 0.0) -> dict:
    """ONE pass, both directions. `merge` is `data.py`'s own merger — this module never writes the store.

    Order matters and is deliberate: PUSH first, then PULL. Pushing our newer rows before reading means
    the pull sees what we just wrote and finds nothing to undo; the other order would fetch a stale
    Google row, merge it in, and then push the result back — laundering a stale value into a fresh one.
    """
    sv = svc()
    if sv is None:
        return {"ok": False, "error": "el conector de contactos no está disponible"}

    from . import data as _d                       # lazy: data.py imports THIS module at the top
    out: dict = {"pushed": 0, "created": 0, "failed": 0}

    if sv.can_write("google-contacts"):
        mine = [c for c in db.get("contacts", []) if _is_ours(c, since)]
        if mine:
            res = sv.push(mine, "google-contacts")
            if res.get("ok"):
                out.update({"pushed": res.get("sent", 0), "created": res.get("created", 0),
                            "failed": res.get("failed", 0), "problems": res.get("problems") or []})
            else:
                # A refused push is NOT a refused sync: the pull half still works and is still worth
                # doing. It is reported, never swallowed.
                out["pushError"] = str(res.get("error") or "")

    got = sv.fetch("google-contacts")
    if not got.get("ok"):
        if out.get("pushed") or out.get("created"):
            out["ok"] = True
            out["pullError"] = str(got.get("error") or "")
            return out
        return {"ok": False, "error": str(got.get("error") or "no se pudo leer Google Contacts")}

    counts = merge(db, got.get("contacts") or [])
    out.update(counts)
    out["ok"] = True
    out["truncated"] = bool(got.get("truncated"))
    db.setdefault("sync", {})["last"] = _time.time()
    db["sync"]["lastResult"] = {k: v for k, v in out.items() if k != "problems"}
    _ = _d                                          # the lazy import is the contract, not a use
    return out


def _is_ours(c: dict, since: float) -> bool:
    """A row the operator touched after the last completed sync — the only rows worth pushing.

    A contact with no `googleId` that he created here counts too: it does not exist on Google yet, so
    «newer than the last sync» is trivially true of it.
    """
    if not str(c.get("name") or "").strip():
        return False
    if not str(c.get("googleId") or "").strip():
        return True
    try:
        # `updated` is a DATE (YYYY-MM-DD), not a timestamp — it is what the store has always written.
        # Comparing a date against a clock means a row edited today re-pushes on every pass of the same
        # day. That is idempotent (the etag read-modify-write writes the same values) and it is the
        # conservative direction: pushing twice costs a request, missing an edit loses it.
        stamp = _time.mktime(_time.strptime(str(c.get("updated") or "1970-01-01"), "%Y-%m-%d"))
    except Exception:
        return False
    return stamp >= (since - 86400)
