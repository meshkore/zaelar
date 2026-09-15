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
from . import gcontacts

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


# V2-683 — CHANNELS. A contact carries how to REACH them, per platform, so «escríbele a Iván» has an
# answer that is not a guess. Shape and the rules for choosing one live in `widgets/directory.py` (the layer
# module every outbound door asks); this file only stores and validates what it is told.
_PLATFORMS = ("whatsapp", "telegram", "email")


def _platform(v) -> str:
    n = _norm(v)
    return n if n in _PLATFORMS else ""


def _channel_row(raw) -> dict | None:
    """One channel from whatever shape the caller used. A row with no platform, or with neither a handle nor
    a chatId, is not a channel: it carries no way to reach anybody and storing it would make
    `channel_for` answer «yes, by Telegram» over nothing."""
    if not isinstance(raw, dict):
        return None
    p = _platform(raw.get("platform"))
    if not p:
        return None
    handle = str(raw.get("handle") or raw.get("address") or raw.get("phone") or "").strip()
    chat_id = str(raw.get("chatId") or "").strip()
    if not handle and not chat_id:
        return None
    row = {"platform": p, "handle": handle, "chatId": chat_id,
           "source": str(raw.get("source") or "operator").strip() or "operator",
           "volume": int(raw.get("volume") or 0)}
    try:
        row["last_seen"] = float(raw.get("last_seen") or 0)
    except (TypeError, ValueError):
        row["last_seen"] = 0.0
    return row


def _channels_in(payload: dict) -> list[dict]:
    """`channels` as a list of rows, or a single `{platform, handle}` — deduped by platform, last one wins."""
    raw = payload.get("channels")
    if raw is None:
        return []
    rows = raw if isinstance(raw, (list, tuple)) else [raw]
    out: dict[str, dict] = {}
    for r in rows:
        row = _channel_row(r)
        if row:
            out[row["platform"]] = row
    return list(out.values())


def _same_channel(a: dict, b: dict) -> bool:
    """Do these two channel rows name the SAME account? Platform plus either identity, `@` and case aside."""
    if _norm(a.get("platform")) != _norm(b.get("platform")):
        return False
    for k in ("chatId", "handle"):
        for j in ("chatId", "handle"):
            x, y = _norm(str(a.get(k) or "")).lstrip("@"), _norm(str(b.get(j) or "")).lstrip("@")
            if x and x == y:
                return True
    return False


def _owner_of_channel(contacts: list[dict], rows: list[dict]) -> dict | None:
    """The contact who ALREADY holds one of these accounts, if any (V2-693).

    An account is a stronger identity than a name: «Cryptonite» and «Pruebas Zaelar» are two names for one
    Telegram user, and `add_contact` deduped on name+city alone — so the second name made a second row. The
    operator found it himself: «¿cómo vamos a tener dos contactos que tienen el mismo nickname de Telegram?».
    Two owners is not a merge, it is an ambiguity, and this answers None so the caller writes nothing."""
    hits = [c for c in contacts
            if any(_same_channel(ch, row) for ch in c.get("channels") or [] for row in rows)]
    return hits[0] if len(hits) == 1 else None


def _merge_channel(c: dict, row: dict) -> None:
    """Set one channel on a contact, keeping what the new row does not say (an operator fixing a handle must
    not erase the chatId the traffic already taught us, and vice versa)."""
    chs = c.setdefault("channels", [])
    old = next((ch for ch in chs if ch.get("platform") == row["platform"]), None)
    if old is None:
        chs.append(row)
        return
    for k in ("handle", "chatId"):
        if row.get(k):
            old[k] = row[k]
    old["source"] = row.get("source") or old.get("source") or "operator"
    if row.get("volume"):
        old["volume"] = row["volume"]
    if row.get("last_seen"):
        old["last_seen"] = row["last_seen"]


def _reach(c: dict) -> list[dict]:
    """Every channel this contact is reachable by, INCLUDING the ones derived from a plain stored address —
    `widgets/directory.py` owns that judgement, and asking it here is what keeps what the brain reads and
    what the sending door does from drifting apart. Falls back to the raw list if the layer is unavailable."""
    try:
        from .. import directory
        return directory.channels(c)
    except Exception:
        return [ch for ch in (c.get("channels") or []) if ch.get("platform")]


def _match_imported(contacts: list[dict], inc: dict) -> dict | None:
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
            if _platform(payload.get("preferred")):
                existing["preferred"] = _platform(payload.get("preferred"))
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
                 "channels": incoming, "preferred": _platform(payload.get("preferred")),
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
        # V2-699 — EMPTYING a field is its own gesture, and it has to be, because the loop above ignores ""
        # on purpose: a model that omits a field, or sends it blank because it did not hear it, must never
        # wipe what the operator typed. The card is a deliberate hand on a deliberate field, so it names the
        # field it is clearing instead of relying on an empty string nobody can tell from an accident.
        for k in _clear_in(payload):
            if k in _FIELDS and k != "name":   # a nameless contact cannot be found again by voice or by eye
                c[k] = ""
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
        if _platform(payload.get("preferred")):
            c["preferred"] = _platform(payload.get("preferred"))
        c["updated"] = now
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
            c["updated"] = now
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
        c["updated"] = now
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": {"contact": _public(c), "channel": p}})
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

    if action in ("connect", "disconnect"):
        if action == "connect":
            return gcontacts.connect(str(payload.get("tier") or ""), str(payload.get("origin") or ""))
        res = gcontacts.disconnect()
        d = view_data(q)
        d.update({"ok": bool(res.get("ok")), "result": res})
        return d

    if action in ("sync_contacts", "import_google"):
        # `import_google` is kept as an alias: it shipped in the manifest for one build and a model that
        # learned it must not start getting «acción desconocida» for asking the same thing.
        res = gcontacts.sync(db, merge=_merge_imported,
                             since=float((db.get("sync") or {}).get("last") or 0.0))
        if not res.get("ok"):
            return {"ok": False, "error": str(res.get("error") or "no se pudo sincronizar")}
        store.save(WIDGET_ID, db)
        d = view_data(q)
        d.update({"ok": True, "result": res})
        return d

    return {"ok": False, "error": f"acción desconocida: {action}"}


def _merge_imported(db: dict, rows: list[dict]) -> dict:
    """Fold Google's side into ours. The MERGE lives here, not in the connector: this store is the only
    module that knows which fields the OPERATOR typed himself.

    **His edits win.** Google only FILLS IN what is empty here — a pass that overwrote a field he had
    fixed would silently undo the correction, and he would have no way to tell which of the two surfaces
    was lying. The other direction (his newer rows reaching Google) is `gcontacts.sync`'s push half, which
    has already run by the time this is called.
    """
    contacts = db.setdefault("contacts", [])
    now = time.strftime("%Y-%m-%d")
    added = updated_n = unchanged = 0
    for inc in rows or []:
        c = _match_imported(contacts, inc)
        if c is None:
            cid = f"c{db.get('next_id', 1)}"
            db["next_id"] = int(db.get("next_id", 1)) + 1
            c = {"id": cid, "kind": inc.get("kind") or "person", "name": inc["name"],
                 "city": inc.get("city", ""), "address": inc.get("address", ""),
                 "phone": inc.get("phone", ""), "email": inc.get("email", ""),
                 "notes": inc.get("notes", ""), "groups": list(inc.get("groups") or []),
                 "favorite": bool(inc.get("favorite")), "channels": [], "preferred": "",
                 "parentId": "", "created": now, "updated": now,
                 "source": "google", "googleId": inc.get("googleId", "")}
            contacts.append(c)
            added += 1
            continue
        # HIS EDITS WIN. Google only FILLS IN what is empty here — it never overwrites a field the
        # operator typed, because a second import would silently undo every correction he had made,
        # and he would have no way to tell which of the two surfaces was lying.
        touched = False
        for k in ("city", "address", "phone", "email", "notes"):
            if inc.get(k) and not str(c.get(k) or "").strip():
                c[k] = inc[k]
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
            c["updated"] = now
            updated_n += 1
        else:
            unchanged += 1

    return {"added": added, "updated": updated_n, "unchanged": unchanged, "read": len(rows or [])}
