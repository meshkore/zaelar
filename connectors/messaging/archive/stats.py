# What a viewer or a doctor reads off the archive: the health line, one page of rows, and the counts behind an
# overview (V2-808: the memory viewer never asks for a whole store).
import logging
import os
import time

from connectors.messaging.archive.lookup import _fts_term


def stats() -> dict:
    """Row count and time span — the health line a brief or a doctor can print."""
    try:
        r = _svc._conn().execute("SELECT COUNT(*) n, MIN(ts) lo, MAX(ts) hi FROM messages").fetchone()
        return {"messages": r["n"], "oldest": r["lo"], "newest": r["hi"]}
    except Exception:  # noqa: BLE001
        return {"messages": 0, "oldest": None, "newest": None}


#: Rows one `page()` call returns at most (V2-808: the memory viewer never asks for a whole store).
PAGE_CAP = 200


def page(*, platform: str | None = None, q: str | None = None, before_ts: float | None = None,
         before_id: int | None = None, limit: int = 50) -> dict:
    """One page of the archive, newest first, for a viewer. The cursor is the last row's `(ts, id)`: ids follow
    insertion order and a backfill inserts old messages late, so `ts` orders and `id` breaks ties. `q` walks the
    FTS index. Returns `{items, more, next: {ts, id}}`; never raises."""
    n = max(1, min(int(limit or 50), PAGE_CAP))
    try:
        where, args = [], []
        if q and str(q).strip():
            where.append("id IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?)")
            args.append(" ".join(_fts_term(t) for t in str(q).split()))
        if platform:
            where.append("platform = ?"); args.append(str(platform))
        if before_ts is not None and before_id:
            where.append("(ts < ? OR (ts = ? AND id < ?))"); args += [float(before_ts), float(before_ts), int(before_id)]
        sql = ("SELECT id, platform, chat_name, is_group, sender, direction, ts, body, media_type FROM messages"
               + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY ts DESC, id DESC LIMIT ?")
        rows = [dict(r) for r in _svc._conn().execute(sql, (*args, n + 1)).fetchall()]
    except Exception as e:  # noqa: BLE001
        logging.getLogger("zaelar.messaging.archive").warning("page failed: %s", e)
        return {"items": [], "more": False, "next": None}
    items = rows[:n]
    nxt = {"ts": items[-1]["ts"], "id": items[-1]["id"]} if items else None
    return {"items": items, "more": len(rows) > n, "next": nxt}


def totals(week_s: int = 7 * 86400) -> dict:
    """COUNTs for an overview: per platform, the last week, and the file's size on disk. Never raises."""
    try:
        conn = _svc._conn()
        by = {r["platform"]: int(r["n"]) for r in
              conn.execute("SELECT platform, COUNT(*) n FROM messages GROUP BY platform").fetchall()}
        week = int(conn.execute("SELECT COUNT(*) FROM messages WHERE ts >= ?",
                                (time.time() - week_s,)).fetchone()[0])
    except Exception as e:  # noqa: BLE001
        logging.getLogger("zaelar.messaging.archive").warning("totals failed: %s", e)
        by, week = {}, 0
    size = 0
    for suffix in ("", "-wal"):
        p = _svc._db_path() + suffix
        size += os.path.getsize(p) if os.path.exists(p) else 0
    return {"total": sum(by.values()), "by_platform": by, "week": week, "bytes": size}


def per_day(days: int = 30) -> list[dict]:
    """Messages per local day over the last `days`. Never raises."""
    try:
        rows = _svc._conn().execute(
            "SELECT date(ts,'unixepoch','localtime') d, COUNT(*) n FROM messages WHERE ts >= ? GROUP BY d ORDER BY d",
            (time.time() - max(1, min(int(days or 30), 366)) * 86400,)).fetchall()
        return [{"day": r["d"], "messages": int(r["n"])} for r in rows]
    except Exception as e:  # noqa: BLE001
        logging.getLogger("zaelar.messaging.archive").warning("per-day count failed: %s", e)
        return list()


# Read back through the facade (V2-778 F1): tests patch `_db_path`/`_conn` there.
from connectors.messaging import archive as _svc  # noqa: E402
