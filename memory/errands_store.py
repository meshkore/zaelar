"""memory/errands_store.py — the STORAGE for an errand with a third party (V2-683).

The `errands`/`errand_threads` tables and nothing else: what opens an errand, what wakes it and when it
closes are RULES, and they live in `nucleo/errands/`. This module stores and reads, exactly as the
workflows facade does for its own table.

Why its own module rather than more of `memory/api.py`: the facade is at its size ceiling and the
architecture ratchet asks for a module instead of a higher number — and this concern is cohesive enough to
be one. It is still the memory package's own boundary, so the rule `nucleo/workflows/` follows holds
unchanged: nothing outside `memory/` touches `db`, the schema or the retriever.

Every function fails SOFT. A ledger that raises would take down the turn that was merely trying to
remember something, which is the opposite of what it is for.
"""
from __future__ import annotations

import json
import time

from . import db as _db_mod


# Facade access, the same boundary `workflows` keeps: `nucleo/errands/` owns the RULES (what opens one, what
# wakes it, when it closes) and never touches memory internals. These functions store and read, nothing else.
def errand_put(row: dict) -> None:
    """Insert or replace one errand. The caller composes the row; this writes it."""
    now = int(time.time())
    try:
        _db_mod.get_db().execute(
            "INSERT INTO errands (id, kind, title, objective, mandate, state, unknowns, done_when, "
            "last_inbound, wake_count, trace_id, deadline, expires_at, created_at, updated_at, closed_at, "
            "outcome) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, title=excluded.title, "
            "objective=excluded.objective, mandate=excluded.mandate, state=excluded.state, "
            "unknowns=excluded.unknowns, done_when=excluded.done_when, last_inbound=excluded.last_inbound, "
            "wake_count=excluded.wake_count, deadline=excluded.deadline, expires_at=excluded.expires_at, "
            "updated_at=excluded.updated_at, closed_at=excluded.closed_at, outcome=excluded.outcome",
            (str(row.get("id")), str(row.get("kind") or "generic"), str(row.get("title") or ""),
             str(row.get("objective") or ""),
             json.dumps(row.get("mandate") or {}, ensure_ascii=False), str(row.get("state") or "contacting"),
             json.dumps(row.get("unknowns") or [], ensure_ascii=False),
             json.dumps(row.get("done_when") or {}, ensure_ascii=False),
             str(row.get("last_inbound") or ""), int(row.get("wake_count") or 0),
             str(row.get("trace_id") or ""), int(row.get("deadline") or 0), int(row.get("expires_at") or 0),
             int(row.get("created_at") or now), now, int(row.get("closed_at") or 0) or None,
             str(row.get("outcome") or "")))
    except Exception:
        pass


def errands_where(states: tuple = ("contacting", "negotiating", "agreed", "gathering"),
                  limit: int = 50) -> list[dict]:
    """Errands in any of those states, oldest first. The default is «still live»."""
    if not states:
        return []
    marks = ",".join("?" for _ in states)
    try:
        rows = _db_mod.get_db().query(
            f"SELECT * FROM errands WHERE state IN ({marks}) ORDER BY created_at ASC LIMIT ?",
            (*states, int(limit)))
        return [dict(r) for r in rows]
    except Exception:
        return []


def errand_get(errand_id: str) -> dict | None:
    try:
        rows = _db_mod.get_db().query("SELECT * FROM errands WHERE id=?", (str(errand_id),))
        return dict(rows[0]) if rows else None
    except Exception:
        return None


def errand_bind_thread(platform: str, chat_id, errand_id: str, contact_id: str = "") -> bool:
    """Give this conversation to this errand. Returns False when another errand already holds it — the
    primary key is what makes «one errand per thread» structural instead of a rule somebody remembers."""
    try:
        _db_mod.get_db().execute(
            "INSERT INTO errand_threads (platform, chat_id, errand_id, contact_id, bound_at) "
            "VALUES (?,?,?,?,?)",
            (str(platform), str(chat_id), str(errand_id), str(contact_id or ""), int(time.time())))
        return True
    except Exception:
        return False


def errand_rebind_thread(platform: str, chat_id, errand_id: str, contact_id: str = "") -> bool:
    """Hand this conversation to another errand, REPLACING whoever holds it. The caller decides whether the
    incumbent may be displaced (`nucleo.errands.bind` only calls this over an errand that is already DONE);
    the primary key still keeps «one errand per conversation» structural."""
    try:
        _db_mod.get_db().execute(
            "INSERT OR REPLACE INTO errand_threads (platform, chat_id, errand_id, contact_id, bound_at) "
            "VALUES (?,?,?,?,?)",
            (str(platform), str(chat_id), str(errand_id), str(contact_id or ""), int(time.time())))
        return True
    except Exception:
        return False


def errand_for_thread(platform: str, chat_id) -> dict | None:
    """The errand this conversation belongs to, or None. ONE indexed lookup — it runs per inbound message."""
    try:
        rows = _db_mod.get_db().query(
            "SELECT e.* FROM errand_threads t JOIN errands e ON e.id = t.errand_id "
            "WHERE t.platform=? AND t.chat_id=?", (str(platform), str(chat_id)))
        return dict(rows[0]) if rows else None
    except Exception:
        return None


def errand_threads(errand_id: str) -> list[dict]:
    try:
        rows = _db_mod.get_db().query(
            "SELECT platform, chat_id, contact_id, bound_at FROM errand_threads WHERE errand_id=?",
            (str(errand_id),))
        return [dict(r) for r in rows]
    except Exception:
        return []


def errand_unbind(errand_id: str) -> None:
    """Release this errand's conversations — called when it closes, so a later message about something else
    does not wake a finished errand."""
    try:
        _db_mod.get_db().execute("DELETE FROM errand_threads WHERE errand_id=?", (str(errand_id),))
    except Exception:
        pass


def errand_forget(errand_id: str = "") -> None:
    """Drop an errand (or all of them — the tests, and a factory reset)."""
    try:
        if errand_id:
            _db_mod.get_db().execute("DELETE FROM errand_threads WHERE errand_id=?", (str(errand_id),))
            _db_mod.get_db().execute("DELETE FROM errands WHERE id=?", (str(errand_id),))
        else:
            _db_mod.get_db().execute("DELETE FROM errand_threads")
            _db_mod.get_db().execute("DELETE FROM errands")
    except Exception:
        pass
