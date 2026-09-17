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
    contacts = visible(db)
    favs = sum(1 for c in contacts if c.get("favorite"))
    if not contacts:
        return ("Directorio VACÍO: 0 contactos, 0 favoritos. Si tu memoria dice otra cosa, MANDA este "
                "bloque: no afirmes que hay entradas guardadas.")
    lines = [f"Directorio COMPLETO y real: {len(contacts)} entradas, {favs} favoritas (⭐). Para contar o "
             "listar lo guardado, MANDA este bloque sobre tu memoria y sobre la conversación: lo que no "
             "esté aquí NO está guardado."]
    circles = [c for c in contacts if c.get("kind") == "group"]
    if circles:
        # The brain has to be able to answer «¿en qué grupos estoy?» and «escribe al grupo de la familia»
        # from the card rather than from memory — the same reason the counts above are stated out loud.
        lines.append("GRUPOS reales (chats y clusters, se les puede escribir): " + " · ".join(
            f"«{g.get('name')}» ({g.get('platform') or g.get('source') or '?'}"
            + (f", {len(g.get('members') or [])} miembros" if g.get("membersKnown", True)
               else ", miembros no enumerables")
            + ")" for g in circles[:8]) + ".")
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
        # The primary number, and HOW MANY more there are — never all of them: this block rides every turn
        # while the card is open, and a company with six lines would spend the budget on one row. «+2 más»
        # is what stops «tel 900111222» reading as «that is the only number we hold» (the whole list is one
        # `read_query` away, which is the door a question about somebody goes through).
        tels = model.values(c, "phones") or ([c["phone"]] if c.get("phone") else [])
        if tels:
            extra.append(f"tel {tels[0]}" + (f" (+{len(tels) - 1} más)" if len(tels) > 1 else ""))
        # V2-683 — by WHICH channel he can be written to, and which one is his. Platforms only (a handle is
        # personal data and the sending door reads it from the store, not from here). Asked through
        # `directory` rather than read raw, so a stored address counts as the email channel it is — the
        # digest and the door that sends must never disagree about who is reachable.
        chans = [str(ch.get("platform")) for ch in _reach(c)]
        if chans:
            pref = str(c.get("preferred") or "")
            extra.append("canales: " + ", ".join((p + " (preferido)") if p == pref else p for p in chans))
        if c.get("notes"):
            extra.append(str(c["notes"])[:80])
        if extra:
            row += " (" + "; ".join(x for x in extra if x) + ")"
        lines.append(row)
    if len(contacts) > 15:
        lines.append(f"… y {len(contacts) - 15} entradas más (la tarjeta las enseña todas).")
    return "\n".join(lines)


def visible(db: dict) -> list[dict]:
    """The rows the operator is meant to SEE. One reader, because «hidden» has to mean the same thing in
    the card, in the brain's digest, in the voice index and in whoever asks next (V2-714).

    A hidden row keeps its `externalIds`, and that mapping is the whole reason hiding beats deleting: the
    next import pass MATCHES it and leaves it alone, instead of bringing the person back and making him
    hide them again forever."""
    return [c for c in (db.get("contacts") or []) if not c.get("hidden")]


def ref_index() -> list[dict]:
    """Items the brain can reference by voice (V2-026): every contact, by name (+city to disambiguate two
    «Juan»s). `field` is the payload key every action uses, so refs resolve without the model guessing ids."""
    out = []
    for c in visible(load_db()):                  # hidden rows stay MAPPED and stop being referenceable
        label = str(c.get("name") or c.get("id"))
        if c.get("city"):
            label += f" ({c['city']})"
        if c.get("kind") == "group":
            # …and a group says so, plus where it lives: «Familia» the WhatsApp chat and «Familia» the
            # label he types are two different things, and the menu has to be able to tell them apart.
            n = len(c.get("members") or [])
            hint = " · ".join(x for x in (str(c.get("platform") or ""),
                                          (f"{n} miembros" if n else "")) if x) or "grupo"
        else:
            hint = ", ".join(c.get("groups") or []) or str(c.get("kind") or "")
        out.append({"id": c["id"], "label": label, "field": "contactId", "hint": hint})
    return out


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
        groups = _groups_in(payload)
        incoming = _channels_in(payload)
        # Name+city first (the operator saying the same person again), then the ACCOUNT — one Telegram
        # username can only belong to one contact, whatever it is called this time (V2-693).
        existing = next((c for c in contacts
                         if _norm(c.get("name")) == _norm(name) and _norm(c.get("city")) == _norm(city)), None)
        if existing is None and incoming:
            existing = _owner_of_channel(contacts, incoming)
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
            for row in incoming:
                _merge_channel(existing, row)
            for key in ("phones", "emails"):
                for row in model.details_in(payload, key) or []:
                    model.add_detail(existing, key, row["value"], row.get("label") or "")
            if _platform(payload.get("preferred")):
                existing["preferred"] = _platform(payload.get("preferred"))
            model.normalize(existing)
            _touch(existing, now)
            c, updated = existing, True
        else:
            c = {"id": f"c{db.get('next_id', 1)}", "kind": _kind(payload.get("kind")),
                 "name": name, "city": city,
                 "address": str(payload.get("address") or "").strip(),
                 "phone": str(payload.get("phone") or "").strip(),
                 "email": str(payload.get("email") or "").strip(),
                 "notes": str(payload.get("notes") or "").strip(),
                 "groups": groups, "favorite": _truthy(payload.get("favorite")),
                 "channels": incoming, "preferred": _platform(payload.get("preferred")),
                 "phones": model.details_in(payload, "phones") or [],
                 "emails": model.details_in(payload, "emails") or [],
                 "parentId": "", "created": now, "updated": now, "touchedAt": time.time()}
            model.normalize(c)
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
        # V2-699 — EMPTYING a field is its own gesture, and it has to be, because the loop above ignores ""
        # on purpose: a model that omits a field, or sends it blank because it did not hear it, must never
        # wipe what the operator typed. The card is a deliberate hand on a deliberate field, so it names the
        # field it is clearing instead of relying on an empty string nobody can tell from an accident.
        for k in _clear_in(payload):
            if k in _FIELDS and k != "name":   # a nameless contact cannot be found again by voice or by eye
                c[k] = ""
                # …and the LIST goes with it. `normalize` keeps the scalar in step with the head of its
                # list, so emptying only the scalar would have the next read put the number straight back.
                if k in ("phone", "email"):
                    c[k + "s"] = []
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
        for row in _channels_in(payload):
            _merge_channel(c, row)
        # `phones`/`emails` REPLACE the list (that is what the card's ✕ and its editor send); `add_phone`
        # and `add_email` are the other half, for a sentence that only names one more number.
        for key in ("phones", "emails"):
            rows = model.details_in(payload, key)
            if rows is not None:
                c[key] = rows
                c[model._DETAIL_KEYS[key]] = rows[0]["value"] if rows else ""
        if _platform(payload.get("preferred")):
            c["preferred"] = _platform(payload.get("preferred"))
        model.normalize(c)
        _touch(c, now)
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": {"contact": _public(c)}})
        return d

    if action == "set_channel":
        # V2-683 — «a Iván escríbele por Telegram». The CHANNEL and the PREFERENCE are one gesture because
        # that is how it is said; `preferred` alone (no handle) just moves the preference to a channel that
        # already exists, which is the other half of the same sentence («mejor por WhatsApp»).
        c = _find(db, payload.get("contactId"))
        if not c:
            return {"ok": False, "error": "no encuentro ese contacto — set_channel necesita su `contactId` "
                                          "(pásame el nombre en `item` y lo resuelvo yo)"}
        p = _platform(payload.get("platform"))
        if not p:
            return {"ok": False, "error": "no me ha llegado la plataforma — set_channel necesita `platform` "
                                          "(whatsapp, telegram o email)"}
        handle = str(payload.get("handle") or payload.get("address") or "").strip()
        chat_id = str(payload.get("chatId") or "").strip()
        if _truthy(payload.get("remove")):
            # V2-699 — the card's ✕. It drops the PREFERENCE with the channel: a preferred platform the
            # contact no longer has is a promise the sending door cannot keep, and `channel_for` would fall
            # back silently to a different one, which is the same wrong-recipient family `refs.py` guards.
            c["channels"] = [ch for ch in (c.get("channels") or []) if str(ch.get("platform")) != p]
            if str(c.get("preferred") or "") == p:
                c["preferred"] = ""
            _touch(c, now)
            store.save(WIDGET_ID, db)
            d = view_data(q)
            d.update({"ok": True, "result": {"contact": _public(c), "removed_channel": p}})
            return d
        if handle or chat_id:
            _merge_channel(c, {"platform": p, "handle": handle, "chatId": chat_id,
                               "source": "operator", "volume": 0, "last_seen": 0.0})
        elif not any(ch.get("platform") == p for ch in c.get("channels") or []):
            # Making a channel PREFERRED without saying how to reach it, when we do not know either, would
            # store a preference that no send can honour — and it would read as «done» to him.
            return {"ok": False,
                    "error": f"no tengo ningún {p} suyo — vuelve a llamar a set_channel con `handle` "
                             f"(su usuario, su teléfono o su dirección)"}
        if _truthy(payload.get("preferred"), default=True):
            c["preferred"] = p
        _touch(c, now)
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": {"contact": _public(c), "channel": p}})
        return d

    if action in ("add_phone", "add_email"):
        # V2-715 — «varios teléfonos que estén vinculados a la misma empresa». One action per kind of
        # detail, both directions in one gesture (`remove: true`), the shape `set_channel` already uses:
        # a second action whose only job is to undo the first is a second thing to remember.
        key = "phones" if action == "add_phone" else "emails"
        field = "phone" if action == "add_phone" else "email"
        c = _find(db, payload.get("contactId"))
        if not c:
            return {"ok": False, "error": f"no encuentro ese contacto — {action} necesita su `contactId` "
                                          "(pásame el nombre en `item` y lo resuelvo yo)"}
        value = str(payload.get(field) or payload.get("value") or payload.get("handle") or "").strip()
        if not value:
            return {"ok": False,
                    "error": f"no me ha llegado el dato — vuelve a llamar a {action} con `{field}` "
                             f"(y `label` si te dijo de qué es: «centralita», «móvil»…)"}
        if _truthy(payload.get("remove")):
            changed = model.drop_detail(c, key, value)
        else:
            changed = model.add_detail(c, key, value, str(payload.get("label") or "").strip())
        if changed:
            _touch(c, now)
            store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": {"contact": _public(c), field + "s": model.values(c, key),
                                         "changed": changed}})
        return d

    if action == "show_connectors":
        # The plug button, by voice (V2-715). Every control on this card has to be reachable both ways —
        # «ábreme los conectores de contactos» used to have no action at all, so the model's only move was
        # to show the widget and describe a button the operator was already looking at.
        _push_view(db, {"screen": "connectors"})
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": {"screen": "connectors",
                                         "sources": [{"id": p_["id"], "label": p_.get("label"),
                                                      "status": p_.get("status")}
                                                     for p_ in (d.get("providers") or [])]}})
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
            # …and neither does a GROUP keep a member who is gone (V2-714): the same rule, one relation
            # over. A stale id would paint a member count nobody can open.
            if c["id"] in (x.get("members") or []):
                x["members"] = [m for m in x["members"] if m != c["id"]]
        # V2-701 — the other half of the mirror. His model: «se modifica en un sitio o en otro, todo se
        # sincroniza linealmente y es un espejo». A deletion is a change like any other, and it is the one
        # a pull CANNOT carry: once the row is gone from here there is nothing left to compare, so the
        # intention is written down now and spent by the next push. Queued even when the connection is
        # read-only — the write permission may arrive before he next opens this card, and then it lands.
        gid = str(c.get("googleId") or "").strip()
        if gid:
            pend = db.setdefault("sync", {}).setdefault("pendingDeletes", [])
            if gid not in pend:
                pend.append(gid)
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": {"removed": _public(c)}})
        return d

    if action == "set_favorite":
        c = _find(db, payload.get("contactId"))
        if not c:
            return {"ok": False, "error": "no encuentro ese contacto — set_favorite necesita su `contactId`"}
        c["favorite"] = _truthy(payload.get("favorite"), default=True)
        _touch(c, now)
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": {"contact": _public(c)}})
        return d

    if action == "hide_contact":
        # HIDE, not delete (V2-714). «En local los contactos son editables y se pueden ocultar, se quedan
        # mapeados a las plataformas.» The mapping is the point: a hidden row still matches on the next
        # import, so the person he took off his screen does not come back every pass. Deleting still
        # exists and is still LOCAL — no platform here has an address-book write API.
        c = _find(db, payload.get("contactId"))
        if not c:
            return {"ok": False, "error": "no encuentro ese contacto — hide_contact necesita su `contactId`"}
        c["hidden"] = _truthy(payload.get("hidden"), default=True)
        _touch(c, now)
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": {"contact": _public(c), "hidden": c["hidden"]}})
        return d

    if action == "sync_source":
        # ONE pass of ONE source, on demand. The permanent half is `sources.tick`; this is «trae mis
        # contactos de Telegram ahora».
        from . import sources
        res = sources.sync_now(str(payload.get("source") or "").strip().lower())
        if not res.get("ok"):
            return {**view_data(q), **res}
        d = view_data(q)
        d.update({"ok": True, "result": res})
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
        _touch(c, now)
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": {"contact": _public(c), "parentId": pid}})
        return d

    if action == "show_contact_members":
        c = _find(db, payload.get("contactId"))
        if not c or c.get("kind") != "group":
            return {"ok": False, "error": "eso no es un grupo — pide el grupo por su nombre"}
        rows = [_public(x) for x in visible(db) if x["id"] in (c.get("members") or [])]
        d = view_data(q)
        d.update({"ok": True, "result": {"group": _public(c), "members": rows,
                                         "membersKnown": c.get("membersKnown", True)}})
        return d

    if action == "show_view":
        # THE VIEW IS AN ACTION (V2-540's lesson, applied at birth instead of after the incident): filtering
        # what is on screen has a NAME in the manifest, and the same call ANSWERS the query — the matches ride
        # in `result` so «¿cuál es mi restaurante favorito en Barcelona?» is one call, not a promise.
        sel = {}
        for k in ("group", "city", "query", "kind", "source"):
            v = str(payload.get(k) or "").strip()
            if v:
                sel[k] = v
        fav = payload.get("favorites")
        if fav is not None and str(fav).strip() != "":
            sel["favorites"] = _truthy(fav)
        # The HIDDEN shelf, by voice (V2-715). It is the one rail section that reads a different pool, and
        # without this «enséñame los que oculté» had no answer at all — which is what makes hiding feel
        # like a delete with a softer word.
        hid = _truthy(payload.get("hidden"))
        if hid:
            sel["hidden"] = True
        pool = [c for c in (db.get("contacts") or []) if c.get("hidden")] if hid else visible(db)
        _push_view(db, sel)
        store.save(WIDGET_ID, db)
        found = _matches(pool, group=sel.get("group", ""), city=sel.get("city", ""),
                         favorites=sel.get("favorites"), query=sel.get("query", ""),
                         kind=sel.get("kind", ""), source=sel.get("source", ""))
        d = view_data(q)
        d.update({"ok": True, "result": {"count": len(found), "matches": [_public(c) for c in found[:12]],
                                         **({"hidden": True} if hid else {})}})
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

    if action in ("connect", "disconnect"):
        if action == "connect":
            return gcontacts.connect(str(payload.get("tier") or ""), str(payload.get("origin") or ""))
        res = gcontacts.disconnect()
        d = view_data(q)
        d.update({"ok": bool(res.get("ok")), "result": res})
        return d

    if action == "set_auto":
        # V2-701 — «eso debería quedarse conectado de forma permanente». The switch is the state; the
        # background tick reads it every pass, so turning it off stops the next one with nothing to cancel.
        on = _truthy(payload.get("auto"), default=True)
        # V2-714 — ONE switch per source, and the same switch for both halves of it: «no vamos a poner dos
        # opciones… un botón de sincronizar que se queda activado». Naming a source routes to that source;
        # naming none keeps meaning Google, which is what every existing caller means.
        src = str(payload.get("source") or "").strip().lower()
        if src:
            from . import sources as _src
            res = _src.set_auto(src, on)
            d = view_data(q)
            d.update({"ok": bool(res.get("ok")), "result": res} if res.get("ok") else res)
            return d
        db.setdefault("sync", {})["auto"] = on
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": {"auto": on}})
        return d

    if action in ("sync_contacts", "import_google"):
        # `import_google` is kept as an alias: it shipped in the manifest for one build and a model that
        # learned it must not start getting «acción desconocida» for asking the same thing.
        res = gcontacts.sync(db, merge=gcontacts.merge_imported, remove=gcontacts.drop_deleted,
                             since=float((db.get("sync") or {}).get("last") or 0.0))
        if not res.get("ok"):
            return {"ok": False, "error": str(res.get("error") or "no se pudo sincronizar")}
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": res})
        return d

    return {"ok": False, "error": f"acción desconocida: {action}"}


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
