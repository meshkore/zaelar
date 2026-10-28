"""memory/notices_store.py — the notice ledger's storage: the `notices` and `push_devices` tables and nothing else.

The rules live in the owner (`nucleo/pulse/notices.py` — which channel, when to retry, what «covered» means); this module
only reads and writes the rows, and is reached through the facade (`memory.api.notices`), never imported directly.
Rows come back as plain dicts.
"""
from __future__ import annotations

from . import db as _db

_NOTICE_COLS = ("kind", "title", "body", "url", "state", "channel", "attempts", "next_try_at", "delivered_at",
                "seen_at", "detail")


def _d():
    return _db.get_db()


def get(nid) -> dict | None:
    r = _d().query_one("SELECT * FROM notices WHERE id=?", (int(nid),))
    return dict(r) if r else None


def by_key(key: str) -> dict | None:
    r = _d().query_one("SELECT * FROM notices WHERE dedupe_key=?", (str(key),))
    return dict(r) if r else None


def recent(limit: int = 30, state: str = "") -> list[dict]:
    if state:
        rows = _d().query("SELECT * FROM notices WHERE state=? ORDER BY created_at DESC LIMIT ?", (state, int(limit)))
    else:
        rows = _d().query("SELECT * FROM notices ORDER BY created_at DESC LIMIT ?", (int(limit),))
    return [dict(r) for r in rows]


def insert(key: str, kind: str, title: str, body: str, url: str, created_at: int, detail: str) -> int:
    """A new `owed` row. Raises on a duplicate `dedupe_key` (the UNIQUE constraint is the guarantee)."""
    return _d().execute(
        "INSERT INTO notices (dedupe_key, kind, title, body, url, state, created_at, detail) "
        "VALUES (?, ?, ?, ?, ?, 'owed', ?, ?)", (key, kind, title, body, url, int(created_at), detail))


def update(nid, **fields) -> None:
    cols = [k for k in fields if k in _NOTICE_COLS]
    if not cols:
        return
    _d().execute(f"UPDATE notices SET {', '.join(f'{k}=?' for k in cols)} WHERE id=?",
                 (*(fields[k] for k in cols), int(nid)))


def owed_due(now: int, limit: int = 20) -> list[dict]:
    rows = _d().query("SELECT * FROM notices WHERE state='owed' AND next_try_at IS NOT NULL AND next_try_at<=? "
                      "ORDER BY created_at LIMIT ?", (int(now), int(limit)))
    return [dict(r) for r in rows]


def owed_all(limit: int = 20) -> list[dict]:
    rows = _d().query("SELECT * FROM notices WHERE state='owed' ORDER BY created_at LIMIT ?", (int(limit),))
    return [dict(r) for r in rows]


# ── devices ───────────────────────────────────────────────────────────────────────────────────────────────────
def device_upsert(did: str, endpoint: str, p256dh: str, auth: str, dev: str, platform: str, installed: bool,
                  created_at: int) -> None:
    _d().execute(
        "INSERT INTO push_devices (id, endpoint, p256dh, auth, dev, platform, installed, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET p256dh=excluded.p256dh, auth=excluded.auth, "
        "dev=excluded.dev, platform=excluded.platform, installed=excluded.installed, fail_count=0",
        (did, endpoint, p256dh, auth, dev, platform, 1 if installed else 0, int(created_at)))


def device_delete(did: str) -> None:
    _d().execute("DELETE FROM push_devices WHERE id=?", (did,))


def devices_public() -> list[dict]:
    """Every device WITHOUT its endpoint or keys (a capability URL never leaves the ledger)."""
    rows = _d().query("SELECT id, dev, platform, installed, created_at, last_ok_at, fail_count FROM push_devices "
                      "ORDER BY created_at")
    return [dict(r) for r in rows]


def devices_all() -> list[dict]:
    return [dict(r) for r in _d().query("SELECT * FROM push_devices")]


def device_ok(did: str, now: int) -> None:
    _d().execute("UPDATE push_devices SET last_ok_at=?, fail_count=0 WHERE id=?", (int(now), did))


def device_failed(did: str) -> None:
    _d().execute("UPDATE push_devices SET fail_count=fail_count+1 WHERE id=?", (did,))
