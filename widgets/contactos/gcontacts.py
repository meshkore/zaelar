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
        # Said out loud so the card can promise the interval it actually runs at instead of a number
        # somebody typed into a label and nobody kept in step with the scheduler.
        "every": int(PERIOD),
        "blockedDeletes": int(s.get("blockedDeletes") or 0),
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


def sync(db: dict, *, merge, since: float = 0.0, remove=None) -> dict:
    """ONE pass, both directions. `merge` is `data.py`'s own merger — this module never writes the store.

    Order matters and is deliberate: PUSH first, then PULL. Pushing our newer rows before reading means
    the pull sees what we just wrote and finds nothing to undo; the other order would fetch a stale
    Google row, merge it in, and then push the result back — laundering a stale value into a fresh one.

    The pull half carries a SYNC TOKEN (V2-701), so a pass over a quiet address book is one round-trip
    that returns nothing rather than six pages of 2 685 people. That is what makes a permanent sync
    affordable at all — and it is also what lets the merge know whether a row it is looking at is
    something Google CHANGED (`full=False`) or just something Google happens to hold.
    """
    sv = svc()
    if sv is None:
        return {"ok": False, "error": "el conector de contactos no está disponible"}

    from . import data as _d                       # lazy: data.py imports THIS module at the top
    out: dict = {"pushed": 0, "created": 0, "failed": 0}
    state = db.setdefault("sync", {})

    if sv.can_write("google-contacts"):
        mine = [c for c in db.get("contacts", []) if _is_ours(c, since)]
        gone = list(state.get("pendingDeletes") or [])
        if mine or gone:
            res = sv.push(mine, "google-contacts", gone=gone)
            if res.get("ok"):
                out.update({"pushed": res.get("sent", 0), "created": res.get("created", 0),
                            "failed": res.get("failed", 0), "problems": res.get("problems") or [],
                            "deletedThere": res.get("removed", 0)})
                _mark_pushed(mine)
                # The queue is spent only on a pass that actually reached Google. Clearing it on a refused
                # push would lose the deletion silently and let the next full read resurrect the row.
                state["pendingDeletes"] = []
            else:
                # A refused push is NOT a refused sync: the pull half still works and is still worth
                # doing. It is reported, never swallowed.
                out["pushError"] = str(res.get("error") or "")

    got = sv.fetch("google-contacts", sync_token=str(state.get("token") or ""))
    if not got.get("ok"):
        if out.get("pushed") or out.get("created"):
            out["ok"] = True
            out["pullError"] = str(got.get("error") or "")
            return out
        return {"ok": False, "error": str(got.get("error") or "no se pudo leer Google Contacts")}

    counts = merge(db, got.get("contacts") or [], authoritative=not got.get("full", True))
    out.update(counts)
    if remove is not None:
        out["removed"] = remove(db, got.get("deleted") or [])
    out["ok"] = True
    out["truncated"] = bool(got.get("truncated"))
    out["incremental"] = not got.get("full", True)
    # A token is only worth keeping when the pass that produced it actually completed: a truncated read
    # stopped at `max_pages` with people it never saw, and a token stamped there would make the pages it
    # skipped invisible FOREVER. Dropping it costs one full re-read next pass.
    state["token"] = "" if got.get("truncated") else str(got.get("syncToken") or "")
    state["last"] = _time.time()
    state["lastResult"] = {k: v for k, v in out.items() if k != "problems"}
    _ = _d                                          # the lazy import is the contract, not a use
    return out


#: How often a linked account is polled while automatic sync is on. Not the widget's tick: the scheduler
#: wakes this module far more often than it talks to Google, so the period can change here without
#: touching the manifest, and a card reopening does not trigger a pass.
PERIOD = 60.0


def tick(ctx) -> None:
    """The permanent half (V2-701). The operator: «el tema de la sincronización de contactos no es algo que
    deberíamos hacer de forma puntual… eso debería quedarse conectado de forma permanente».

    It is a POLL because the People API has no push for a personal account — there is no webhook to
    subscribe to, so «permanently connected» is, physically, a cheap question asked on a timer. The sync
    token is what makes it cheap; without it this would be six pages a minute and would have to be a
    button, which is exactly the shape he rejected.
    """
    sv, o = svc(), _oauth()
    if sv is None or o is None or not o.tokens_present("google-contacts"):
        return
    from . import data as _d
    db = _d.load_db()
    s = db.get("sync") or {}
    if not bool(s.get("auto", True)):
        return
    if (_time.time() - float(s.get("last") or 0.0)) < PERIOD:
        return
    res = sync(db, merge=_d._merge_imported, since=float(s.get("last") or 0.0), remove=_d._drop_deleted)
    if not res.get("ok"):
        # A pass that failed still moves `last`, or a dead token would make every tick retry forever and
        # hammer Google from a loop nobody is watching. The error rides in `lastResult` for the card.
        db.setdefault("sync", {})["last"] = _time.time()
        db["sync"]["lastResult"] = {"error": str(res.get("error") or "")[:200]}
        ctx.save(db)
        return
    ctx.save(db)


def _mark_pushed(rows: list[dict]) -> None:
    """Stamp the rows we have just sent, so the next pass does not send them again.

    ⚠️ This is what turns a one-off button into something that can run every minute. The old test was a
    DATE comparison, and a date says «edited today» for the rest of the day — harmless when the operator
    pressed a button now and then, a PATCH per contact per minute once the same code runs on a timer.
    """
    now = _time.time()
    for c in rows:
        c["pushedAt"] = now
        c.setdefault("touchedAt", now)   # a legacy row leaves the date regime the first time it is sent


def _is_ours(c: dict, since: float) -> bool:
    """A row the operator changed and Google has not been told about — the only rows worth pushing.

    A contact with no `googleId` that he created here counts too: it does not exist on Google yet.

    Precise where the record allows it: `touchedAt` is stamped by every local write and `pushedAt` by every
    successful push, so «he changed it since we sent it» is one comparison of two clocks. Rows written
    before either existed fall back to the original DATE rule — once, because a successful push stamps
    them and moves them onto the precise path.
    """
    if not str(c.get("name") or "").strip():
        return False
    if not str(c.get("googleId") or "").strip():
        return True
    touched, pushed = float(c.get("touchedAt") or 0.0), float(c.get("pushedAt") or 0.0)
    if touched or pushed:
        return touched > pushed
    try:
        # `updated` is a DATE (YYYY-MM-DD), not a timestamp — it is what the store wrote before V2-701.
        stamp = _time.mktime(_time.strptime(str(c.get("updated") or "1970-01-01"), "%Y-%m-%d"))
    except Exception:
        return False
    return stamp >= (since - 86400)
