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

from .. import store
from . import gcontacts
from . import model

# A QUESTION about somebody is answered from the RECORD, through `widgets/directory.resolve` — not from the
# summary below, which is a first page without handles by design (`widgets/contactos/lookup.py`, V2-704).
# Re-exported because `read_query` is the seam `nucleo/flash/widget_read` looks for, on `data.py`, for every
# widget.
from .lookup import read_query  # noqa: F401,E402 — re-export

WIDGET_ID = "contactos"

# Store schema version (lazy migration on read — see store.load). Bump when the shape changes.
#   1 → 2 (V2-715): `phones` / `emails` — several per contact, each with a free label («centralita»,
#   «móvil»), because a company is not one number. `phone` / `email` stay as the PRIMARY and are kept in
#   step by `model.normalize`, so the four modules outside this widget that read the scalar keep reading it.
DB_VERSION = 2


def _seed() -> dict:
    # Built fresh on every call: a module-level dict with a list inside is shallow-copied by dict() and a
    # later append would mutate the module seed (real shipped bug, V2-366).
    return {"contacts": [], "next_id": 1}


def _migrate(db: dict, from_v: int) -> dict:
    """Lift the scalar `phone`/`email` into their lists (v1 → v2).

    ⚠️ **Row by row, each inside its own `try`.** `store.load` degrades a migration that RAISES to the seed
    — which here is an EMPTY directory, and the next save would persist it. This runs over the operator's
    real address book (2 688 rows the day it was written), so one malformed row must cost that row's
    normalisation and nothing else: a directory that loses everything to a stray value is the worst failure
    this widget has available to it.
    """
    if from_v < 2:
        for c in db.get("contacts") or []:
            try:
                model.normalize(c)
            except Exception:                              # noqa: BLE001 — see the warning above
                continue
    return db


def load_db() -> dict:
    if not store.exists(WIDGET_ID):
        store.save(WIDGET_ID, _seed())
    return store.load(WIDGET_ID, _seed(), version=DB_VERSION, migrate=_migrate)


def _touch(c: dict, now: str = "") -> None:
    """Mark a row as changed BY THE OPERATOR — the date he reads, and the clock the sync needs (V2-701).

    ⚠️ `updated` is a DATE, and a date cannot say «he changed it after we last sent it»: it says «today»
    for the rest of the day. That was survivable while syncing was a button he pressed now and then; with
    a pass every minute it is a PATCH per edited contact per minute. `touchedAt` is the precise half, and
    only local writes set it — an import filling in an empty field is Google's doing, not his, and stamping
    it there would push Google's own value straight back at it in a loop.
    """
    c["updated"] = now or time.strftime("%Y-%m-%d")
    c["touchedAt"] = time.time()


# ── the RECORD SHAPE lives in `model.py` (V2-715) ───────────────────────────────────────────────────────
# This file is the STORE and the action table; what a directory entry IS — kinds, group labels, channels,
# phones, e-mails, and the predicate every filter asks — is a layer underneath both, and it is asked by the
# card, by `show_view` and by the digest alike. The private names are kept as aliases because they are what
# every existing caller and test in this house already reaches for.
_norm = model.norm
_kind = model.kind
_truthy = model.truthy
_groups_in = model.groups_in
_group_matches = model.group_matches
_matches = model.matches
_platform = model.platform
_PLATFORMS = model.PLATFORMS
_channel_row = model.channel_row
_channels_in = model.channels_in
_same_channel = model.same_channel
_owner_of_channel = model.owner_of_channel
_merge_channel = model.merge_channel


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


def _reach(c: dict) -> list[dict]:
    """Every channel this contact is reachable by, INCLUDING the ones derived from a plain stored address —
    `widgets/directory.py` owns that judgement, and asking it here is what keeps what the brain reads and
    what the sending door does from drifting apart. Falls back to the raw list if the layer is unavailable."""
    try:
        from .. import directory
        return directory.channels(c)
    except Exception:
        return [ch for ch in (c.get("channels") or []) if ch.get("platform")]


def _public(c: dict) -> dict:
    """The compact row an action RESULT carries back to the brain — enough to answer by voice, never the
    whole record (the full data travels in view_data, and a result is read inside a prompt)."""
    out = {"id": c.get("id"), "name": c.get("name"), "kind": c.get("kind")}
    for k in ("city", "phone", "groups"):
        if c.get(k):
            out[k] = c[k]
    if c.get("favorite"):
        out["favorite"] = True
    if c.get("flags"):
        out["flags"] = list(c["flags"])
    # The PLATFORMS only, never the handles: this row is read inside a prompt, and a phone number or an
    # address in there is personal data travelling for no reason — the door that sends already reads the
    # handle from the store itself.
    chans = [str(ch.get("platform")) for ch in _reach(c)]
    if chans:
        out["channels"] = chans
    if c.get("preferred"):
        out["preferred"] = c["preferred"]
    return out


def view_data(q: str = "") -> dict:
    """Everything the render needs: the full archive (the widget filters client-side), the derived group rail,
    the cities present, and the pushed view (if fresh)."""
    db = load_db()
    contacts = visible(db)
    labels: dict[str, dict] = {}
    cities: dict[str, str] = {}
    for c in contacts:
        for g in c.get("groups") or []:
            k = _norm(g)
            e = labels.setdefault(k, {"id": g, "count": 0})
            e["count"] += 1
        ct = str(c.get("city") or "").strip()
        if ct:
            cities.setdefault(_norm(ct), ct)
    # V2-714 — the two senses of «group», kept apart on purpose. `groups` is the LABEL rail he files with;
    # `circles` are the real groups: a Telegram or WhatsApp chat, a MeshKore cluster. They have members and
    # you can write to them, so they are rows of the directory, not tags on it.
    circles = [{"id": c["id"], "name": c.get("name"), "platform": c.get("platform") or c.get("source") or "",
                "subtype": c.get("subtype") or "group", "members": len(c.get("members") or []),
                "membersKnown": c.get("membersKnown", True)}
               for c in contacts if c.get("kind") == "group"]
    return {
        "contacts": contacts,
        "groups": sorted(labels.values(), key=lambda g: (-g["count"], _norm(g["id"]))),
        "circles": sorted(circles, key=lambda g: (-g["members"], _norm(g["name"] or ""))),
        "cities": sorted(cities.values(), key=_norm),
        "favorites_count": sum(1 for c in contacts if c.get("favorite")),
        # The hidden ones travel TOO (V2-715). `contacts` is what he is meant to see, and hiding stays the
        # right default; but a row he can neither see nor reach is a row he cannot bring back, and «quita
        # este de la lista» must be undoable from the same card that did it.
        "hidden_rows": [c for c in (db.get("contacts") or []) if c.get("hidden")],
        "hidden_count": sum(1 for c in (db.get("contacts") or []) if c.get("hidden")),
        "count": len(contacts),
        "view": _fresh_view(db),
        # V2-699 — the subheader strip and the connectors screen, the agenda's own contract: which
        # sources exist, which are linked, and what the sync can actually do right now.
        "providers": gcontacts.providers(),
        "sync": gcontacts.sync_state(db),
    }


def visible(db: dict) -> list[dict]:
    """The rows the operator is meant to SEE. One reader, because «hidden» has to mean the same thing in
    the card, in the brain's digest, in the voice index and in whoever asks next (V2-714).

    A hidden row keeps its `externalIds`, and that mapping is the whole reason hiding beats deleting: the
    next import pass MATCHES it and leaves it alone, instead of bringing the person back and making him
    hide them again forever."""
    return [c for c in (db.get("contacts") or []) if not c.get("hidden")]



def _find(db: dict, cid) -> dict | None:
    for c in db.get("contacts", []):
        if c.get("id") == cid:
            return c
    return None


_FIELDS = ("name", "city", "address", "phone", "email", "notes")


def _clear_in(payload: dict) -> list[str]:
    """Which fields this call EMPTIES. A list, or one name, or a comma string — the card sends one, the
    voice never sends this at all (see the note at the call site)."""
    raw = payload.get("clear")
    if raw is None:
        return []
    parts = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    return [str(p or "").strip().lower() for p in parts if str(p or "").strip()]


# refactor2710-12 T-03 — what the brain reads (the turn digest, the rows a sentence names, the voice index) lives
# in `digest.py`; the runtime and the turn look these names up HERE.
from .digest import people_named, prompt_digest, ref_index  # noqa: E402,F401 — re-export


# V2-778 F1-12 — the action handlers live in `actions.py`, imported back under their names (that module
# reads this one).
from .actions import (  # noqa: E402,F401
    _a_add_contact, _a_update_contact, _a_set_channel, _a_add_channel, _a_show_sources, _a_remove_contact,
    _a_set_favorite, _a_hide_contact, _a_sync_source, _a_link_contact, _a_show_contact_members, _a_show_view,
    _a_show_contact, _a_set_auto, _a_sync_contacts, _a_set_flag, _a_restore_contact)


# V2-778 F1-12 — one function per action (in `actions.py`), and `apply_action` is the table lookup. Each body
# is the branch it was, moved verbatim; the contract gate reads the table's keys
# (`widgets/validator._table_actions`).


ACTIONS = {
    "add_contact": _a_add_contact,
    "update_contact": _a_update_contact,
    "set_channel": _a_set_channel,
    "add_phone": _a_add_channel,
    "add_email": _a_add_channel,
    "show_sources": _a_show_sources,
    "remove_contact": _a_remove_contact,
    "set_favorite": _a_set_favorite,
    "set_flag": _a_set_flag,
    "restore_contact": _a_restore_contact,
    "hide_contact": _a_hide_contact,
    "sync_source": _a_sync_source,
    "link_contact": _a_link_contact,
    "show_contact_members": _a_show_contact_members,
    "show_view": _a_show_view,
    "show_contact": _a_show_contact,
    "set_auto": _a_set_auto,
    "sync_contacts": _a_sync_contacts,
    "import_google": _a_sync_contacts,
}


def apply_action(action: str, payload: dict | None = None) -> dict:
    """Widget actions. Every payload may carry `q` — the instance the canvas stamps into every click
    (V2-540: it is always `q`, never anything else); this widget is single-instance, so it is accepted and
    ignored, but a handler that crashed on it would break every button on the card."""
    payload = model.with_category(payload or {})       # a category is a label said in a field of its own
    q = str(payload.get("q") or "")
    db = load_db()
    contacts = db.setdefault("contacts", [])
    now = time.strftime("%Y-%m-%d")
    handler = ACTIONS.get(action) if isinstance(action, str) else None
    if handler is None:
        return {"ok": False, "error": f"acción desconocida: {action}"}
    return handler(action, payload, q, db, contacts, now)


#: The GOOGLE merge moved to `gcontacts.py` (V2-714). It belongs there: that module is already «the Google
#: Contacts GLUE» and already holds the who-wins-a-conflict rule, and the day this file grew a SECOND
#: importer — the import-only one in `imports.py` — keeping a Google-shaped merge in the middle of the data
#: layer was what made the file unreadable. Names kept so every existing caller and test still finds them.
_merge_imported = gcontacts.merge_imported
_match_imported = gcontacts.match_imported
_drop_deleted = gcontacts.drop_deleted


def tick(ctx) -> None:
    """Keep the linked account in step (V2-701). The scheduler's contract needs this name in THIS file;
    the body lives in `gcontacts.py`, the same extraction the agenda made for `gcal.tick`."""
    gcontacts.tick(ctx)
    from . import sources as _src           # V2-714: the import-only sources, on their own cadence
    _src.tick(ctx)
