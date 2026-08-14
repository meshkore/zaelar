"""memory/journal.py — `journal` table for task continuity (V2-005 · T71).

Central memory already declares the `journal` table (V2-002 · schema.py): id · title · status
(`pending`|`in_progress`|`done`) · detail · created · updated. This module is its **access face** (direct CRUD, hot
path — sub-ms sqlite, no queue): used by the **orchestrator-loop scheduler** (`nucleo/scheduler.py`) to back
scheduled tasks ("own cron" replacing Hermes's), and available for SlowBrain task-continuity journal (V2-006/007).

`detail` stores a free JSON blob (for the scheduler: `{"kind":"scheduled","schedule":{...},"prompt":...}`). It is
serialized/deserialized here so the caller handles dicts, not strings.
"""
from __future__ import annotations

import json
import time

from . import db as _db

_STATUSES = ("pending", "in_progress", "done")


def _now() -> int:
    from .clock import now
    return now()


def _row_to_dict(row) -> dict:
    d = dict(row)
    raw = d.get("detail")
    if raw:
        try:
            d["detail"] = json.loads(raw)
        except Exception:
            d["detail"] = {"_raw": raw}
    else:
        d["detail"] = {}
    return d


def add(title: str, *, status: str = "pending", detail: dict | None = None) -> int:
    """Create a journal entry and return its id. `detail` is serialized to JSON."""
    if status not in _STATUSES:
        status = "pending"
    ts = _now()
    blob = json.dumps(detail or {}, ensure_ascii=False)
    return _db.get_db().execute(
        "INSERT INTO journal (title, status, detail, created, updated) VALUES (?,?,?,?,?)",
        (title or "", status, blob, ts, ts),
    )


def get(jid: int) -> dict | None:
    row = _db.get_db().query_one("SELECT * FROM journal WHERE id=?", (int(jid),))
    return _row_to_dict(row) if row is not None else None


def list_entries(status: str | None = None, limit: int = 200) -> list[dict]:
    """List entries (newest first), filtering by status if requested."""
    if status:
        rows = _db.get_db().query(
            "SELECT * FROM journal WHERE status=? ORDER BY updated DESC LIMIT ?", (status, int(limit)))
    else:
        rows = _db.get_db().query(
            "SELECT * FROM journal ORDER BY updated DESC LIMIT ?", (int(limit),))
    return [_row_to_dict(r) for r in rows]


def update(jid: int, *, title: str | None = None, status: str | None = None,
           detail: dict | None = None) -> None:
    """Update the given fields (None values remain untouched). `detail` REPLACES the whole blob."""
    sets, params = [], []
    if title is not None:
        sets.append("title=?"); params.append(title)
    if status is not None and status in _STATUSES:
        sets.append("status=?"); params.append(status)
    if detail is not None:
        sets.append("detail=?"); params.append(json.dumps(detail, ensure_ascii=False))
    if not sets:
        return
    sets.append("updated=?"); params.append(_now())
    params.append(int(jid))
    _db.get_db().execute(f"UPDATE journal SET {', '.join(sets)} WHERE id=?", tuple(params))


def remove(jid: int) -> None:
    _db.get_db().execute("DELETE FROM journal WHERE id=?", (int(jid),))
