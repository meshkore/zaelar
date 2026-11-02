"""rules — ONE scoped table for every standing rule and preference (V2-806).

A rule and a preference are the same thing: a row with a scope, a kind (`gate` — applied by code; `pref` — a value
an owner reads, or a `note` the model reads), a key, a value, optional exceptions, a source (`default` | `user`),
his own words, a creation time, an active flag and an optional `until`.

    from rules import path, gate, value
    anchors = path(cls="messaging.send_new", channel="email", widget="mensajeria", action="send_draft")
    gate(anchors)                 # "allow" | "ask" | "never" | ""

Design: `.meshkore/docs/architecture/zaelar-rules.md`. The safety rails (a missing fact, a doubt about which,
the radius of a sweep) are NOT rules and live in `nucleo/consent.decide`, out of this table's reach.
"""
from __future__ import annotations

import time
import uuid

from . import cascade as _cascade
from . import defaults as _defaults
from . import scope as _scope
from . import store as _store
from .scope import GLOBAL, SEARCH, class_scope, covers, norm, path, split_key  # noqa: F401 — the public grammar

KINDS = ("gate", "pref")
ALLOW, ASK, NEVER, GATE_VALUES = _cascade.ALLOW, _cascade.ASK, _cascade.NEVER, _cascade.GATE_VALUES
NOTE, EXCLUDED = _cascade.NOTE, _cascade.EXCLUDED


def all_rows(*, include_defaults: bool = True) -> list[dict]:
    """Every row: the factory defaults (built from genesis, never stored) and the stored ones."""
    return (_defaults.rows() if include_defaults else []) + _store.rows()


def resolve(anchors, *, now: float | None = None) -> dict:
    """The cascade over a request's path: `{"values", "rules", "notes"}` (see `rules/cascade.py`)."""
    return _cascade.resolve(all_rows(), list(anchors or [(0, GLOBAL)]), now=now)


def value(anchors, key: str, default=None, *, now: float | None = None):
    v = resolve(anchors, now=now)["values"]
    return v.get(key, default)


def gate(anchors, *, now: float | None = None) -> str:
    """The `consent` gate for this path: 'allow' | 'ask' | 'never' | '' (no row covers it)."""
    v = str(value(anchors, "consent", "", now=now) or "").strip().lower()
    return v if v in GATE_VALUES else ""


def excluded(anchors, *, now: float | None = None) -> list[tuple[str, dict]]:
    """The names his rules rule out on this path, each with the row that rules it out (V2-838) — what a door that
    shows him things (the results sheet) leaves out and names as the reason. Defaults declare no exclusion."""
    out, seen = [], set()
    for r in _cascade.covering(_store.rows(), list(anchors or [(0, GLOBAL)]), now=now):
        if r["key"] != EXCLUDED:
            continue
        for name in (r["value"] if isinstance(r["value"], list) else [r["value"]]):
            n = " ".join(str(name or "").split())
            if n and n.lower() not in seen:
                seen.add(n.lower())
                out.append((n, r))
    return out


def deciding_rule(anchors, key: str = "consent", *, now: float | None = None) -> dict | None:
    """The row that won `key` for this path — what a listing or an event names as the reason."""
    return resolve(anchors, now=now)["rules"].get(key)


# ── writes ──────────────────────────────────────────────────────────────────────────────────────────────────

def _norm_text(t: str) -> str:
    return " ".join(str(t or "").lower().split())


def add(scope: str, kind: str, key: str, value, *, text: str = "", source: str = "user", except_=(),
        until: float | None = None, origin: str = "", rule_id: str = "") -> dict:
    """Store one row. A user row for a key code applies REPLACES his earlier row at the same scope, key and
    exceptions (one value per place); a note — or an exclusion, whose rows add up — replaces only an identical
    sentence at the same scope."""
    sc = _scope.norm(scope)
    kind = kind if kind in KINDS else "pref"
    excepts = sorted({_scope.norm(e) for e in (except_ or []) if str(e).strip()})
    for old in _store.rows():
        if old["source"] != source or old["scope"] != sc or old["key"] != key:
            continue
        same = (_norm_text(old["text"]) == _norm_text(text)) if key in _cascade.ACCUMULATE else (sorted(old["except"]) == excepts)
        if same:
            _store.delete(old["id"])
    row = {"id": rule_id or f"r_{uuid.uuid4().hex[:10]}", "scope": sc, "kind": kind, "key": key, "value": value,
           "except": excepts, "source": source, "text": str(text or "").strip(), "created_at": time.time(),
           "active": True, "until": until, "origin": origin}
    return _store.put(row)


def remove(rule_id: str) -> dict | None:
    """Delete a stored row by id. A default is not stored and cannot be deleted (it can be overridden)."""
    row = _store.get(rule_id)
    if row and _store.delete(rule_id):
        return row
    return None


def clear(scope: str, key: str, *, source: str = "user") -> list[dict]:
    """Delete every stored row of this source at exactly this scope and key. Returns what was removed."""
    sc = _scope.norm(scope)
    gone = [r for r in _store.rows() if r["source"] == source and r["scope"] == sc and r["key"] == key]
    for r in gone:
        _store.delete(r["id"])
    return gone


def set_active(rule_id: str, active: bool) -> dict | None:
    row = _store.get(rule_id)
    if not row:
        return None
    row["active"] = bool(active)
    return _store.put(row)


def set_value(rule_id: str, value) -> dict | None:
    """Edit a row's value. A default's edit is a user row at the same scope and key — the factory row stays."""
    row = _store.get(rule_id) or next((r for r in _defaults.rows() if r["id"] == rule_id), None)
    if not row:
        return None
    if row["source"] == "default":
        return add(row["scope"], row["kind"], row["key"], value, text=row.get("text") or "")
    row["value"] = value
    return _store.put(row)


def get(rule_id: str) -> dict | None:
    return _store.get(rule_id) or next((r for r in _defaults.rows() if r["id"] == rule_id), None)


def _reset_for_tests() -> None:
    _store._reset_for_tests()
