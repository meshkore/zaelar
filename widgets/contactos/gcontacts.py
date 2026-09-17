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
# V2-714 — Telegram and WhatsApp are here because a connector may serve more than one family now
# (`registry.serves`), and because he asked for it by name: «en el widget de contactos quiero que aparezcan
# los iconos de WhatsApp y de Telegram y que se vea si están conectados o no». They keep living in
# Mensajería too, on purpose: «no me importa que el conector viva duplicado en varios widgets».
_SOURCES = (("google-contacts", "Google Contacts"), ("telegram", "Telegram"), ("whatsapp", "WhatsApp"),
            ("icloud", "iCloud (Apple)"), ("carddav", "CardDAV (Outlook, Fastmail…)"))


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
            # `serves`, not `family ==`: one source can belong to two families (V2-714), and asking the
            # registry instead of comparing a string here is what stops this strip and the settings tab
            # disagreeing about whether Telegram is a contact source.
            if registry.serves(d, "contactos"):
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
    # …and what each one can actually DO for this card. A source that imports contacts carries its own
    # switch; one that only holds messages would light up an icon with nothing behind it.
    try:
        from . import sources as _src
        from . import data as _d
        st = _src.state(_d.load_db())
        for row in out:
            if row["id"] in _src.KNOWN:
                row["imports"] = True
                row["sync"] = dict(st.get(row["id"]) or {})
    except Exception:  # noqa: BLE001
        pass
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


# ── THE GOOGLE MERGE (moved here from `data.py`, V2-714) ────────────────────────────────────────────────
# It lived in the data layer while Google was the only source. It is Google's CONTRACT — two-way, «whoever
# touched it last wins», a sync token deciding when Google may replace instead of fill — and the day a
# second, IMPORT-ONLY source arrived (`imports.py`, whose rule is the opposite) the two sitting in one file
# was the thing nobody could read. `_norm`/`_touch`/`store`/`time` come from `data` lazily, the same way
# everything else in this module reaches it.


# ⚠️ MOVING CODE BYTE FOR BYTE CHANGES ITS GLOBALS, and this batch paid that lesson again: the block below
# came from `data.py`, where `time`, `store`, `_norm` and `_touch` are module-level. Here `time` is imported
# as `_time` and the other three do not exist at all, so it raised `NameError` on the first real sync.
# Bound explicitly rather than star-imported: a lazy `from .data import *` would make the direction of this
# dependency invisible, and `data` imports THIS module at its top.
import time                                              # noqa: E402 — the moved block's own name for it


def _model():
    """The record shape, lazily — `model.py` is a leaf and this module is imported BY `data.py`."""
    from . import model
    return model


def _norm(s):
    from .data import _norm as _n
    return _n(s)


def _touch(c, now):
    from .data import _touch as _t
    return _t(c, now)


class _StoreProxy:
    """`store.save(...)` as the moved block spells it, resolved through `data` so there is ONE store."""

    def __getattr__(self, name):
        from .data import store as _s
        return getattr(_s, name)


store = _StoreProxy()


def match_imported(contacts: list[dict], inc: dict) -> dict | None:
    """Which existing contact this Google person IS, or None for somebody new (V2-699).

    Three keys, in descending order of how much they PROVE — and the order is the whole point, because
    every one of them can be right while the ones below it are wrong:

      1. `googleId` — the same resource we imported last time. Survives him renaming the person here.
      2. the email address, wherever it lives (the stored field OR an email channel). An address is an
         account, so two rows sharing one are one person — the same rule V2-693 settled for Telegram.
      3. name + city, normalized — `add_contact`'s own rule, so the two doors agree.
      4. the name ALONE, but only when exactly ONE contact here carries it. This is what makes a second
         import safe: `add_contact` can demand the city because the operator is looking at the answer,
         while Google routinely knows a city he never typed — so «Marta Ruiz» with no city here and
         «Marta Ruiz, Soria» there would otherwise import as a SECOND Marta every single time. When two
         contacts share the name it stops: adding a duplicate he can merge beats silently folding two
         people into one, which he cannot undo.
    """
    gid = str(inc.get("googleId") or "").strip()
    if gid:
        for c in contacts:
            if str(c.get("googleId") or "").strip() == gid:
                return c
    mail = _norm(inc.get("email"))
    if mail:
        for c in contacts:
            if _norm(c.get("email")) == mail:
                return c
            for ch in c.get("channels") or []:
                if str(ch.get("platform")) == "email" and _norm(ch.get("handle")) == mail:
                    return c
    nm, city = _norm(inc.get("name")), _norm(inc.get("city"))
    if not nm:
        return None
    for c in contacts:
        if _norm(c.get("name")) == nm and _norm(c.get("city")) == city:
            return c
    same_name = [c for c in contacts if _norm(c.get("name")) == nm]
    return same_name[0] if len(same_name) == 1 else None


def merge_imported(db: dict, rows: list[dict], *, authoritative: bool = False) -> dict:
    """Fold Google's side into ours. The MERGE lives here, not in the connector: this store is the only
    module that knows which fields the OPERATOR typed himself.

    **His edits win.** Google only FILLS IN what is empty here — a pass that overwrote a field he had
    fixed would silently undo the correction, and he would have no way to tell which of the two surfaces
    was lying. The other direction (his newer rows reaching Google) is `gcontacts.sync`'s push half, which
    has already run by the time this is called.

    `authoritative` is the one case where Google may REPLACE a value instead of only filling a blank, and
    it is narrow on purpose (V2-701): the row arrived through a SYNC TOKEN, which means Google is telling
    us it changed since we last looked, AND our copy has nothing pending («whoever touched it last wins»,
    the rule this connector has answered conflicts with since V2-699). A row he has edited and we have not
    sent yet is still his — it is waiting its turn in the push half, and letting Google win here would
    delete the edit before it ever left the house. A FULL re-read is never authoritative: there, «changed»
    is unknown, and treating every row as fresh would undo his corrections wholesale on the first pass.
    """
    contacts = db.setdefault("contacts", [])
    now = time.strftime("%Y-%m-%d")
    added = updated_n = unchanged = 0
    for inc in rows or []:
        c = match_imported(contacts, inc)
        if c is None:
            cid = f"c{db.get('next_id', 1)}"
            db["next_id"] = int(db.get("next_id", 1)) + 1
            c = {"id": cid, "kind": inc.get("kind") or "person", "name": inc["name"],
                 "city": inc.get("city", ""), "address": inc.get("address", ""),
                 "phone": inc.get("phone", ""), "email": inc.get("email", ""),
                 "notes": inc.get("notes", ""), "groups": list(inc.get("groups") or []),
                 "favorite": bool(inc.get("favorite")), "channels": [], "preferred": "",
                 "phones": list(inc.get("phones") or []), "emails": list(inc.get("emails") or []),
                 "parentId": "", "created": now, "updated": now,
                 "source": "google", "googleId": inc.get("googleId", "")}
            _model().normalize(c)
            contacts.append(c)
            added += 1
            continue
        # HIS EDITS WIN. Google only FILLS IN what is empty here — it never overwrites a field the
        # operator typed, because a second import would silently undo every correction he had made,
        # and he would have no way to tell which of the two surfaces was lying.
        #
        # …unless this row reached us through a sync token AND we have nothing pending on it: then Google
        # touched it last and Google wins, which is what makes this a SYNC rather than a repeated import.
        takes_over = authoritative and float(c.get("touchedAt") or 0.0) <= float(c.get("pushedAt") or 0.0)
        touched = False
        for k in ("city", "address", "phone", "email", "notes"):
            if inc.get(k) and (takes_over or not str(c.get(k) or "").strip()) and inc[k] != c.get(k):
                c[k] = inc[k]
                touched = True
        if takes_over and inc.get("name") and inc["name"] != c.get("name"):
            c["name"] = inc["name"]
            touched = True
        # V2-715 — the OTHER phones and addresses. An ADDITION, always, even when Google is authoritative:
        # a number he typed here is his, and the failure the `takes_over` rule protects against («a second
        # import silently undoes every correction») has exactly the same shape one field over. Google
        # removing a number therefore never removes ours — the card's ✕ is the door for that.
        m = _model()
        for key in ("phones", "emails"):
            for row in inc.get(key) or []:
                if m.add_detail(c, key, row.get("value"), row.get("label") or ""):
                    touched = True
        for g in inc.get("groups") or []:
            if _norm(g) not in {_norm(x) for x in c.get("groups") or []}:
                c.setdefault("groups", []).append(g)
                touched = True
        # A ★ only ever travels ONE way: starring in Google stars here, un-starring there never
        # un-stars the favourite he set on this card.
        if inc.get("favorite") and not c.get("favorite"):
            c["favorite"] = True
            touched = True
        if inc.get("googleId") and not c.get("googleId"):
            c["googleId"] = inc["googleId"]
            touched = True
        if touched:
            # NOT `_touch`: Google filling in a blank is not the operator changing his mind, and stamping
            # `touchedAt` here would make the next push send Google's own value straight back at it.
            c["updated"] = now
            updated_n += 1
        else:
            unchanged += 1

    return {"added": added, "updated": updated_n, "unchanged": unchanged, "read": len(rows or [])}


#: A single pass may never remove more than this share of the address book, nor more than this many rows,
#: whichever bites first. It is not a policy about how many contacts a person deletes in a minute — it is a
#: circuit breaker around OUR OWN code: the failure mode of a sync token gone wrong is «everything looks
#: deleted», and the difference between a bug and a catastrophe is whether anything acted on that.
_DELETE_CAP_SHARE = 0.2
_DELETE_CAP_ROWS = 25


def drop_deleted(db: dict, google_ids: list[str]) -> int:
    """Mirror deletions Google reported, and ONLY the ones that are safe to mirror (V2-701).

    A row he has edited here since we last sent it is not Google's to delete: he touched it last, which is
    the same rule that decides every other conflict in this connector. Those are kept and simply unhooked
    from the pass — they stay in the directory, still carrying their `googleId`, and a later edit will try
    to push and report honestly if Google no longer has them.
    """
    ids = {str(g).strip() for g in (google_ids or []) if str(g).strip()}
    if not ids:
        return 0
    contacts = db.get("contacts") or []
    victims = [c for c in contacts
               if str(c.get("googleId") or "") in ids
               and float(c.get("touchedAt") or 0.0) <= float(c.get("pushedAt") or 0.0)]
    if not victims:
        return 0
    cap = max(_DELETE_CAP_ROWS, int(len(contacts) * _DELETE_CAP_SHARE))
    if len(victims) > cap:
        db.setdefault("sync", {})["blockedDeletes"] = len(victims)
        return 0
    doomed = {c["id"] for c in victims}
    db["contacts"] = [c for c in contacts if c.get("id") not in doomed]
    for x in db["contacts"]:
        if x.get("parentId") in doomed:
            x["parentId"] = ""          # a dangling link paints a dead breadcrumb (same rule as remove_contact)
    db.get("sync", {}).pop("blockedDeletes", None)
    return len(victims)
