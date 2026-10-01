"""memory/workflows_store.py — the `workflows` table: which channel serves an errand domain (V2-594).

Moved out of `memory/api.py` (V2-778 F1, 2026-10-01: the facade had grown past its size ceiling). The functions
are unchanged and `memory.api` re-exports them, so the memory-boundary contract holds: `nucleo/workflows/` still
calls `memory.api.workflows_for` and never touches this module directly.
"""
from __future__ import annotations


from . import db as _db


def workflows_for(domain: str) -> list[dict]:
    """Every row for one errand domain, best rank first — INCLUDING the negative ones, because «the mesh has
    nothing for this» is the answer that saves the most work and the caller has to see it."""
    try:
        rows = _db.get_db().query(
            "SELECT id, domain, channel, rank, status, source, target, evidence, ttl_s, checked_at "
            "FROM workflows WHERE domain=? ORDER BY rank ASC", (domain,))
        return [dict(r) for r in rows]
    except Exception:
        return []


def workflow_upsert(domain: str, channel: str, *, status: str = "active", rank: int = 100,
                    source: str = "learned", target: str = "", evidence: str = "",
                    ttl_s: int = 7 * 24 * 3600) -> None:
    """Write what was just learned about (domain, channel). Unlike `action_map_add` this REPLACES on conflict:
    an action-map row carries a user's veto that a seed upgrade must never overwrite, while a workflow row is
    a perishable observation about the outside world — the whole point is that the newest measurement wins.
    A row the OPERATOR pinned is protected by the caller, which refuses to overwrite `source='operator'`."""
    import time as _time
    now = int(_time.time())
    try:
        _db.get_db().execute(
            "INSERT INTO workflows (domain, channel, rank, status, source, target, evidence, ttl_s, "
            "checked_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(domain, channel) DO UPDATE SET status=excluded.status, rank=excluded.rank, "
            "source=excluded.source, target=excluded.target, evidence=excluded.evidence, "
            "ttl_s=excluded.ttl_s, checked_at=excluded.checked_at",
            (domain, channel, int(rank), status, source, target, evidence, int(ttl_s), now, now))
    except Exception:
        pass


def workflow_hit(entry_id: int) -> None:
    """Bump a row's hit counter (fire-and-forget bookkeeping; the turn never waits on it)."""
    import time as _time
    try:
        _db.get_db().execute("UPDATE workflows SET hits = hits + 1, last_hit_at = ? WHERE id = ?",
                             (int(_time.time()), entry_id))
    except Exception:
        pass


def workflow_forget(domain: str, channel: str = "") -> None:
    """Drop a domain's rows (all of them, or one channel). Used when the operator corrects the route, and by
    the tests. Deliberately a delete and not a status flip: a stale route that is merely disabled would still
    be read by anything that forgets to filter."""
    try:
        if channel:
            _db.get_db().execute("DELETE FROM workflows WHERE domain=? AND channel=?", (domain, channel))
        else:
            _db.get_db().execute("DELETE FROM workflows WHERE domain=?", (domain,))
    except Exception:
        pass
