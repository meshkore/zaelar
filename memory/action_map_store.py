"""memory/action_map_store.py — the `action_map` table: a known phrase per language and the action it runs
(V2-539/545).

Moved out of `memory/api.py` (V2-778 F1, 2026-10-01: the facade was past its size ceiling). The functions are
unchanged and `memory.api` re-exports them, so the memory-boundary contract holds: `nucleo/actionmap/` still calls
`memory.api.action_map_*` and never touches this module directly.
"""
from __future__ import annotations

from . import db as _db  # noqa: F401  (asegura import del paquete; get_db perezoso)



def kv_get(key, default=None):
    """The facade's KV read (the seed version lives there), resolved at call time: the facade imports this module."""
    from . import api
    return api.kv_get(key, default)


def kv_set(key, value):
    from . import api
    return api.kv_set(key, value)


def action_map_active(lang: str) -> list[dict]:
    """Active action-map rows for ONE language (V2-539) — the runtime index loads only these. Facade access
    on purpose (memory-boundary contract): `nucleo/actionmap/` never touches memory internals. Tolerates an
    empty/old DB → []."""
    try:
        rows = _db.get_db().query(
            "SELECT id, phrase, action, source FROM action_map WHERE lang=? AND status='active'", (lang,))
        return [dict(r) for r in rows]
    except Exception:
        return []


def action_map_has_seed(lang: str) -> bool:
    """True if this language's shipped seed pack was already imported (any 'seed' row exists)."""
    try:
        return _db.get_db().query_one(
            "SELECT 1 AS x FROM action_map WHERE lang=? AND source='seed' LIMIT 1", (lang,)) is not None
    except Exception:
        return True  # fail CLOSED for the importer: better to skip a re-import than to double-write blindly


def action_map_seed_version(lang: str) -> int:
    """Which version of the shipped pack this install already imported (0 = none, V2-545).

    `action_map_has_seed` only ever answered «was ANY pack imported», so a better pack shipped later reached
    nobody: every engine that had booted once kept the phrases of the day it was first seeded. This is the
    upgrade key. Legacy installs (rows present, no version recorded) report 1, which is what they hold."""
    try:
        v = kv_get("actionmap.seed_version." + (lang or ""), None)
        if isinstance(v, int):
            return v
        return 1 if action_map_has_seed(lang) else 0
    except Exception:
        return 999   # fail CLOSED for the importer: skipping an upgrade beats re-writing rows blindly


def action_map_set_seed_version(lang: str, version: int) -> None:
    try:
        kv_set("actionmap.seed_version." + (lang or ""), int(version))
    except Exception:
        pass


def action_map_retarget_seed(lang: str, phrase: str, action_json: str) -> bool:
    """Point an UNTOUCHED shipped phrase at a new action (pack upgrade). Returns whether a row changed.

    Only `source='seed'` AND `status='active'` rows move: a phrase the operator disabled, or one the map
    LEARNED, is theirs and survives every upgrade — the same veto rule `action_map_add`'s OR IGNORE encodes."""
    try:
        cur = _db.get_db().query_one(
            "SELECT action FROM action_map WHERE lang=? AND phrase=? AND source='seed' AND status='active'",
            (lang, phrase))
        if not cur or (cur["action"] or "") == action_json:   # sqlite3.Row: index, not .get
            return False
        _db.get_db().execute(
            "UPDATE action_map SET action=? WHERE lang=? AND phrase=? AND source='seed' AND status='active'",
            (action_json, lang, phrase))
        return True
    except Exception:
        return False


def action_map_add(lang: str, phrase: str, action_json: str, *, source: str = "seed",
                   status: str = "active") -> None:
    """Insert one action-map row (idempotent: UNIQUE(lang, phrase) + OR IGNORE — an existing row, including
    one the user disabled or retargeted, is NEVER overwritten; that is how a veto survives a seed upgrade)."""
    import time as _time
    try:
        _db.get_db().execute(
            "INSERT OR IGNORE INTO action_map (lang, phrase, action, source, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (lang, phrase, action_json, source, status, int(_time.time())))
    except Exception:
        pass


def action_map_hit(entry_id: int) -> None:
    """Bump a row's hit counter (fire-and-forget bookkeeping; the turn never waits on it)."""
    import time as _time
    try:
        _db.get_db().execute("UPDATE action_map SET hits = hits + 1, last_hit_at = ? WHERE id = ?",
                             (int(_time.time()), entry_id))
    except Exception:
        pass
