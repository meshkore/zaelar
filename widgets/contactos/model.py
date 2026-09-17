"""model.py — WHAT a directory entry IS, and which ones a filter means (V2-715).

Extracted from `data.py` for the reason the architecture ratchet exists: that file is the store plus the
action table, and the RECORD SHAPE — kinds, group labels, channels, phones, e-mails, and the predicate every
filter asks — is a pure layer underneath both. Nothing here reads or writes the store, and nothing here
imports `data`: it receives rows and answers questions about them.

## The two shapes this module owns

  · **A CHANNEL** (`whatsapp | telegram | email`) is a way to WRITE to somebody. `widgets/directory.py` is
    the layer that decides which one a message goes out by; this only stores and validates.
  · **A DETAIL** (`phones`, `emails`) is a way to REACH somebody that is not a channel of ours — a company
    with a switchboard, a mobile and a billing address (the operator, 2026-09-17: «varios teléfonos que
    estén vinculados a la misma empresa»). Several per contact, each with a free label.

⚠️ **`phone` and `email` stay as the PRIMARY, always in step with the head of their list.** Four modules
outside this widget read `contact["phone"]` — `widgets/directory.py` resolves a spoken number with it,
`connectors/contacts/google_people.py` pushes it — and a list that silently replaced the scalar would make
every one of them read an empty field on a contact that has three numbers. `normalize()` is the one place
that keeps the two in step, in BOTH directions, so a legacy row, a Google import and a card edit all end
up with the same shape.
"""
from __future__ import annotations

import re
import unicodedata

# ── the vocabulary ──────────────────────────────────────────────────────────────────────────────────────

#: The structural kinds (V2-523: one identity set, not per-kind silos). A group LABEL like «restaurantes» is
#: NOT a kind — kinds say what the entry IS, labels say how the operator files it. Unknown values default to
#: person rather than guessing from the label: inferring «place» from a group name would be exactly the kind
#: of hardcoded world-knowledge this house forbids.
#:
#: `group` and `agent` (V2-714) are the same distinction one level up: a Telegram group, a WhatsApp group and
#: a MeshKore cluster have identity, have MEMBERS, come from a platform and can be WRITTEN TO — none of which
#: a label has. An `agent` is what a cluster has instead of people: addressable, not a person.
KINDS = ("person", "company", "place", "group", "agent")

_KINDS = {"person": "person", "persona": "person", "people": "person",
          "place": "place", "lugar": "place", "sitio": "place",
          "company": "company", "empresa": "company", "negocio": "company", "business": "company",
          "group": "group", "grupo": "group", "chat": "group", "cluster": "group", "canal": "group",
          "channel": "group",
          "agent": "agent", "agente": "agent", "bot": "agent"}

#: The three channels a contact can carry, and the order every surface lists them in.
PLATFORMS = ("whatsapp", "telegram", "email")

#: One source, many names. The provider strip calls Google's address book `google-contacts` (that is its
#: connector id); an imported row is stamped `source: "google"` and carries a `googleId`. Without this table
#: the icon the operator clicks and the filter the voice applies would be two different filters wearing one
#: name — which is how a tab shows zero rows over a directory full of them.
_SOURCE_ALIASES = {"google-contacts": "google", "google contacts": "google", "googlecontacts": "google",
                   "gmail": "google", "google-people": "google", "contactos de google": "google",
                   "telegram": "telegram", "whatsapp": "whatsapp", "wasap": "whatsapp",
                   "meshkore": "meshkore", "cluster": "meshkore", "clusters": "meshkore",
                   "icloud": "icloud", "apple": "icloud", "carddav": "carddav"}


def norm(s) -> str:
    """Accent/case-insensitive comparable form, so «Elfo On» and «elfo ón» never pile up as duplicates."""
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def kind(v) -> str:
    return _KINDS.get(norm(v), "person")


def truthy(v, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    n = norm(v)
    if n in ("true", "si", "sí", "yes", "1", "favorito", "favorita", "on"):
        return True
    if n in ("false", "no", "0", "off"):
        return False
    return default


def platform(v) -> str:
    n = norm(v)
    return n if n in PLATFORMS else ""


def source_key(v) -> str:
    """The canonical name of a contact SOURCE, whatever the caller happens to call it."""
    n = norm(v)
    return _SOURCE_ALIASES.get(n, n)


# ── group labels ────────────────────────────────────────────────────────────────────────────────────────

def groups_in(payload: dict) -> list[str]:
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
        if p and norm(p) not in seen:
            seen.add(norm(p))
            out.append(p)
    return out


def group_matches(want: str, contact: dict) -> bool:
    """A spoken group matches a stored label loosely in BOTH directions («fontanero» ↔ «fontaneros»,
    «amigos» ↔ «amigos del trabajo») — containment over normalized forms, never a synonym table."""
    w = norm(want)
    if not w:
        return True
    for g in contact.get("groups") or []:
        gn = norm(g)
        if w in gn or gn in w:
            return True
    return False


# ── phones and e-mails: several, each with a label ──────────────────────────────────────────────────────

_DETAIL_KEYS = {"phones": "phone", "emails": "email"}


def _detail_row(raw, key: str) -> dict | None:
    """One phone/e-mail row from whatever shape the caller used: `"91 555 00 00"`, `{value, label}` or
    `{phone|email|address, label|type}`. A row with no value is not a detail: it is a label pointing at
    nothing, and storing it would paint an empty line on the card for ever."""
    if isinstance(raw, dict):
        value = str(raw.get("value") or raw.get(_DETAIL_KEYS[key]) or raw.get("address") or "").strip()
        label = str(raw.get("label") or raw.get("type") or raw.get("name") or "").strip()
    else:
        value, label = str(raw or "").strip(), ""
    if not value:
        return None
    return {"value": value[:120], "label": label[:40]}


def _detail_id(key: str, value: str) -> str:
    """The comparable identity of a detail. A phone is its DIGITS — «+34 91 555 00 00» and «915550000» are
    one number written twice, and a list that held both would push two of them to Google."""
    if key == "phones":
        digits = re.sub(r"\D", "", str(value or ""))
        return digits[-9:] if len(digits) >= 9 else digits or norm(value)
    return norm(value)


def details_in(payload: dict, key: str):
    """`phones`/`emails` from a payload — a list, a single row, or a comma string. None when the payload
    does not mention them at all, which is NOT the same as an empty list (that one empties the field)."""
    if key not in payload:
        return None
    raw = payload.get(key)
    if raw is None:
        return []
    rows = raw if isinstance(raw, (list, tuple)) else (
        str(raw).split(",") if isinstance(raw, str) else [raw])
    out: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        row = _detail_row(r, key)
        if not row:
            continue
        ident = _detail_id(key, row["value"])
        if ident in seen:
            continue
        seen.add(ident)
        out.append(row)
    return out[:12]                       # a directory entry, not a phone book of its own


def add_detail(contact: dict, key: str, value: str, label: str = "") -> bool:
    """Add one phone/e-mail, keeping what is already there. False when it changes nothing — the caller says
    «ya lo tenías» instead of reporting a write that did not happen."""
    row = _detail_row({"value": value, "label": label}, key)
    if not row:
        return False
    rows = list(contact.get(key) or [])
    ident = _detail_id(key, row["value"])
    for r in rows:
        if _detail_id(key, r.get("value")) == ident:
            if row["label"] and not r.get("label"):
                r["label"] = row["label"]
                contact[key] = rows
                normalize(contact)
                return True
            return False
    rows.append(row)
    contact[key] = rows[:12]
    normalize(contact)
    return True


def drop_detail(contact: dict, key: str, value: str) -> bool:
    """Remove one phone/e-mail by its value. False when it was not there."""
    ident = _detail_id(key, value)
    rows = list(contact.get(key) or [])
    keep = [r for r in rows if _detail_id(key, r.get("value")) != ident]
    if len(keep) == len(rows):
        return False
    contact[key] = keep
    normalize(contact)
    return True


def normalize(contact: dict) -> dict:
    """Keep the list and the PRIMARY scalar in step, in both directions. Called after every write and on
    every migrated row, so a legacy contact, a Google import and a card edit all end up the same shape."""
    for key, scalar in _DETAIL_KEYS.items():
        rows = [r for r in (contact.get(key) or []) if isinstance(r, dict) and str(r.get("value") or "").strip()]
        head = str(contact.get(scalar) or "").strip()
        if rows:
            # The list is the truth; the scalar is its head. If the operator edited the scalar to something
            # the list does not hold, that edit is a NEW primary and goes in front — never silently dropped.
            if head and _detail_id(key, head) not in {_detail_id(key, r["value"]) for r in rows}:
                rows = [{"value": head, "label": ""}] + rows
            elif head and _detail_id(key, rows[0]["value"]) != _detail_id(key, head):
                rows = ([r for r in rows if _detail_id(key, r["value"]) == _detail_id(key, head)]
                        + [r for r in rows if _detail_id(key, r["value"]) != _detail_id(key, head)])
            contact[key] = rows
            contact[scalar] = rows[0]["value"]
        elif head:
            contact[key] = [{"value": head, "label": ""}]
        else:
            contact[key] = []
            contact[scalar] = ""
    return contact


def values(contact: dict, key: str) -> list[str]:
    return [str(r.get("value") or "") for r in (contact.get(key) or []) if str(r.get("value") or "").strip()]


# ── which contacts a filter means ───────────────────────────────────────────────────────────────────────

def source_matches(contact: dict, source: str) -> bool:
    """Does this contact belong to that platform?

    The operator's own definition (2026-09-17): «cuando entramos en Telegram quiero ver solo los contactos
    de Telegram». Belonging is BOTH halves — where the row CAME FROM and where he can REACH the person —
    because a contact typed here by hand and later matched to a Telegram account is as much a Telegram
    contact as one the import brought, and a tab that showed only the imported half would hide exactly the
    people he talks to most.
    """
    s = source_key(source)
    if not s:
        return True
    if source_key(contact.get("source")) == s or source_key(contact.get("platform")) == s:
        return True
    for k in (contact.get("externalIds") or {}):
        if source_key(k) == s:
            return True
    if s == "google" and str(contact.get("googleId") or "").strip():
        return True
    for ch in contact.get("channels") or []:
        if source_key(ch.get("platform")) == s:
            return True
    return False


#: The kind resolver under a second name: `matches` takes a `kind` KEYWORD (the payload's own word, and the
#: one every caller already writes), which shadows the function inside that body.
_kind_of = kind


def matches(contacts: list, *, group: str = "", city: str = "", favorites=None, query: str = "",
            kind: str = "", source: str = "") -> list:
    """The rows a view means. ONE predicate, asked by the card, by `show_view` and by the digest — three
    surfaces of one directory that disagree about what «my Telegram contacts» means is the failure this
    house has paid for more than once."""
    cw, qw = norm(city), norm(query)
    kw = _kind_of(kind) if str(kind or "").strip() else ""
    out = []
    for c in contacts:
        if group and not group_matches(group, c):
            continue
        if kw and _kind_of(c.get("kind")) != kw:
            continue
        if source and not source_matches(c, source):
            continue
        if cw:
            cn = norm(c.get("city"))
            if not (cw in cn or (cn and cn in cw)):
                continue
        if favorites and not c.get("favorite"):
            continue
        if qw:
            hay = norm(" ".join(str(c.get(k) or "") for k in ("name", "city", "address", "notes"))
                       + " " + " ".join(values(c, "phones") + values(c, "emails"))
                       + " " + " ".join(c.get("groups") or [])
                       + " " + " ".join(str(ch.get("handle") or "") for ch in c.get("channels") or []))
            if qw not in hay:
                continue
        out.append(c)
    # Favorites first, then by name — the answer to «¿cuál es mi favorito…?» should lead the list.
    out.sort(key=lambda c: (not c.get("favorite"), norm(c.get("name"))))
    return out


# ── channels: HOW to write to somebody (V2-683) ─────────────────────────────────────────────────────────
# V2-683 — CHANNELS. A contact carries how to REACH them, per platform, so «escríbele a Iván» has an
# answer that is not a guess. Shape and the rules for choosing one live in `widgets/directory.py` (the layer
# module every outbound door asks); this file only stores and validates what it is told.


def channel_row(raw) -> dict | None:
    """One channel from whatever shape the caller used. A row with no platform, or with neither a handle nor
    a chatId, is not a channel: it carries no way to reach anybody and storing it would make
    `channel_for` answer «yes, by Telegram» over nothing."""
    if not isinstance(raw, dict):
        return None
    p = platform(raw.get("platform"))
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


def channels_in(payload: dict) -> list[dict]:
    """`channels` as a list of rows, or a single `{platform, handle}` — deduped by platform, last one wins."""
    raw = payload.get("channels")
    if raw is None:
        return []
    rows = raw if isinstance(raw, (list, tuple)) else [raw]
    out: dict[str, dict] = {}
    for r in rows:
        row = channel_row(r)
        if row:
            out[row["platform"]] = row
    return list(out.values())


def same_channel(a: dict, b: dict) -> bool:
    """Do these two channel rows name the SAME account? Platform plus either identity, `@` and case aside."""
    if norm(a.get("platform")) != norm(b.get("platform")):
        return False
    for k in ("chatId", "handle"):
        for j in ("chatId", "handle"):
            x, y = norm(str(a.get(k) or "")).lstrip("@"), norm(str(b.get(j) or "")).lstrip("@")
            if x and x == y:
                return True
    return False


def owner_of_channel(contacts: list[dict], rows: list[dict]) -> dict | None:
    """The contact who ALREADY holds one of these accounts, if any (V2-693).

    An account is a stronger identity than a name: «Cryptonite» and «Pruebas Zaelar» are two names for one
    Telegram user, and `add_contact` deduped on name+city alone — so the second name made a second row. The
    operator found it himself: «¿cómo vamos a tener dos contactos que tienen el mismo nickname de Telegram?».
    Two owners is not a merge, it is an ambiguity, and this answers None so the caller writes nothing."""
    hits = [c for c in contacts
            if any(same_channel(ch, row) for ch in c.get("channels") or [] for row in rows)]
    return hits[0] if len(hits) == 1 else None


def merge_channel(c: dict, row: dict) -> None:
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
