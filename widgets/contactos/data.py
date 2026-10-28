# Contacts widget — data layer (V2-541). ONE directory for every identity the operator keeps: people, places
# and companies, with freeform group labels, a city, favorites and parent/child links (the people you deal with
# AT a restaurant hang from it). A favourite place IS a directory entry with `favorite` as a flag — never a
# parallel per-kind list or widget (V2-523).
#
# Reads/writes ONLY the widget's isolated store ("widgets/_data/contactos/state.json"). The record shape (kind
# person/place/company, parentId nesting, groupers) keeps a future memory integration a projection, not a rewrite.
import re
import time

from .. import store
from . import gcontacts
from . import model

# A QUESTION about somebody is answered from the RECORD (`lookup.py`, V2-704), not from the digest; re-exported
# because `read_query` is the seam `nucleo/flash/widget_read` looks for on every widget's `data.py`.
from .lookup import read_query  # noqa: F401,E402 — re-export

WIDGET_ID = "contactos"

# Store schema version (lazy migration on read — see store.load). Bump when the shape changes.
#   1 → 2 (V2-715): `phones` / `emails`, several per contact with a free label. `phone` / `email` stay as the
#   PRIMARY, kept in step by `model.normalize`, for the readers outside this widget.
DB_VERSION = 2


def _seed() -> dict:
    # Built fresh on every call: a shallow-copied module-level seed would be mutated by a later append (V2-366).
    return {"contacts": [], "next_id": 1}


def _migrate(db: dict, from_v: int) -> dict:
    """Lift the scalar `phone`/`email` into their lists (v1 → v2).

    ⚠️ **Row by row, each inside its own `try`.** `store.load` degrades a migration that RAISES to the seed — an
    EMPTY directory the next save would persist. One malformed row must cost only that row's normalisation.
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

    ⚠️ `updated` is a DATE, too coarse for «changed after we last sent it» with a sync every minute; `touchedAt`
    is the precise half. Only LOCAL writes set it — stamping an import would push Google's value back in a loop.
    """
    c["updated"] = now or time.strftime("%Y-%m-%d")
    c["touchedAt"] = time.time()


# ── the RECORD SHAPE lives in `model.py` (V2-715) ───────────────────────────────────────────────────────
# This file is the STORE and the action table; what a directory entry IS (kinds, labels, channels, phones,
# e-mails, the filter predicate) is the layer underneath. The private names are aliases callers and tests use.
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


# How long a pushed view stays worth OBEYING (the agenda's `show_day` contract, V2-540): `n` is a monotonic push
# counter the widget re-applies on; freshness is decided HERE, where the clock is, so a reopen next week does not
# land on last week's filter.
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
    """Every channel this contact is reachable by, including those derived from a stored address — asked of
    `widgets/directory.py` so the brain and the sending door never disagree. Falls back to the raw list."""
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
    # The PLATFORMS only, never the handles: this row is read inside a prompt, and the sending door reads the
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
    # Two senses of «group», kept apart: `groups` is the LABEL rail; `circles` are real groups (a chat, a MeshKore
    # cluster) with members you can write to — rows of the directory, not tags (V2-714).
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
        # The hidden ones travel TOO, so a hide is undoable from the same card (V2-715).
        "hidden_rows": [c for c in (db.get("contacts") or []) if c.get("hidden")],
        "hidden_count": sum(1 for c in (db.get("contacts") or []) if c.get("hidden")),
        "count": len(contacts),
        "view": _fresh_view(db),
        # The subheader strip and the connectors screen: which sources exist, are linked, and can sync (V2-699).
        "providers": gcontacts.providers(),
        "sync": gcontacts.sync_state(db),
    }


def visible(db: dict) -> list[dict]:
    """The rows the operator is meant to SEE — one reader, so «hidden» means the same everywhere (V2-714).
    A hidden row keeps its `externalIds`, so the next import MATCHES it and leaves it hidden: why hiding beats
    deleting."""
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


# What the brain reads (turn digest, rows a sentence names, voice index) lives in `digest.py`; looked up HERE.
from .digest import people_named, prompt_digest, ref_index  # noqa: E402,F401 — re-export


# The action handlers live in `actions.py` (which reads this module) (V2-778 F1-12).
from .actions import (  # noqa: E402,F401
    _a_add_contact, _a_update_contact, _a_set_channel, _a_add_channel, _a_show_sources, _a_remove_contact,
    _a_set_favorite, _a_hide_contact, _a_sync_source, _a_link_contact, _a_show_contact_members, _a_show_view,
    _a_show_contact, _a_set_auto, _a_sync_contacts, _a_set_flag, _a_restore_contact)


# `apply_action` is a table lookup; the contract gate reads the table's keys (`widgets/validator._table_actions`).


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
    """Widget actions. Every payload may carry `q`, the instance the canvas stamps into every click (V2-540);
    single-instance here, so it is accepted and ignored — never crashed on."""
    payload = model.with_category(payload or {})       # a category is a label said in a field of its own
    q = str(payload.get("q") or "")
    db = load_db()
    contacts = db.setdefault("contacts", [])
    now = time.strftime("%Y-%m-%d")
    handler = ACTIONS.get(action) if isinstance(action, str) else None
    if handler is None:
        return {"ok": False, "error": f"acción desconocida: {action}"}
    return handler(action, payload, q, db, contacts, now)


#: The GOOGLE merge lives in `gcontacts.py`, beside the who-wins-a-conflict rule (V2-714); aliased for callers.
_merge_imported = gcontacts.merge_imported
_match_imported = gcontacts.match_imported
_drop_deleted = gcontacts.drop_deleted


def tick(ctx) -> None:
    """Keep the linked account in step (V2-701). The scheduler needs this name in THIS file; body in `gcontacts.py`."""
    gcontacts.tick(ctx)
    from . import sources as _src           # V2-714: the import-only sources, on their own cadence
    _src.tick(ctx)
