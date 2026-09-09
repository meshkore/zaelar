#
# archive.py — the CANONICAL communications store (V2-628 F0). Append-only, catalogued, cross-platform.
#
# The design rule it exists to serve (operator directive, 2026-09-09): every domain has exactly ONE canonical
# store. Before this module, every message body was written TWICE and kept NOWHERE: the thread store expires
# (KEEP=40/chat · 14 d · 80 threads — its correct behavior as a replay cache) and the `kind='msg'` pill in
# central memory decays in ~2 days (its correct behavior as recall salience). A question about a message from
# a month ago was unanswerable from any store we control. This log is the permanent home; both existing
# surfaces stay what they are — bounded, EXPIRING views over it.
#
# What it is NOT: not a widget store (no UI state, no queues), not memory (nothing here is a personal fact —
# the heart keeps distilling those through its own door), and not an index of the past (nothing is backfilled
# by default; the log grows forward from the same seams that feed the views, including the on-demand
# `fetch_now`/`load_more` landings, per the V2-624 directive).
#
# Own SQLite file in the domain's data dir, WAL, FTS5 external-content kept in sync by an AFTER INSERT
# trigger — append-only means insert is the only write, so triggers cover the whole contract. Every public
# entry point is best-effort and returns instead of raising: the archive must never break the UI store or a
# connector drain (the same stance `store._to_memory` already takes).
#
import hashlib
import os
import sqlite3
import threading
import time

_LOCK = threading.RLock()
_CONN: sqlite3.Connection | None = None
_PATH: str | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages(
  id        INTEGER PRIMARY KEY,
  platform  TEXT NOT NULL,
  chat_id   TEXT NOT NULL,
  chat_name TEXT NOT NULL DEFAULT '',
  is_group  INTEGER NOT NULL DEFAULT 0,
  sender    TEXT NOT NULL DEFAULT '',
  direction TEXT NOT NULL CHECK(direction IN ('in','out')),
  ts        REAL NOT NULL,
  body      TEXT NOT NULL,
  media_type TEXT NOT NULL DEFAULT '',
  msg_id    TEXT NOT NULL,
  UNIQUE(platform, chat_id, msg_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(platform, chat_id, ts);
CREATE INDEX IF NOT EXISTS idx_messages_ts   ON messages(ts);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
  body, sender, chat_name, content='messages', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, body, sender, chat_name)
  VALUES (new.id, new.body, new.sender, new.chat_name);
END;
"""


def _db_path() -> str:
    from widgets import store as _wstore
    return os.path.join(_wstore.data_dir("mensajeria"), "archive.db")


def _conn() -> sqlite3.Connection:
    global _CONN, _PATH
    path = _db_path()
    with _LOCK:
        if _CONN is not None and _PATH == path:
            return _CONN
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_SCHEMA)
        _CONN, _PATH = conn, path
        return conn


def reset() -> None:
    """Forget the cached connection (tests move the data dir between cases)."""
    global _CONN, _PATH
    with _LOCK:
        if _CONN is not None:
            try:
                _CONN.close()
            except Exception:  # noqa: BLE001
                pass
        _CONN, _PATH = None, None


def _msg_id(m: dict, platform: str, chat_id, ts: float, body: str) -> str:
    """The platform's own id when it gave one; a content hash otherwise. Some transports hand us rows with no
    id (a fetched mail grouped by sender) — those must still be idempotent on a re-fetch, and hashing what
    identifies the message (where, when, what) is exactly that."""
    for k in ("messageId", "id"):
        v = m.get(k)
        if v is not None and str(v).strip():
            return str(v)
    raw = f"{platform}|{chat_id}|{ts:.0f}|{body}"
    return "h:" + hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


def _norm(m: dict, platform: str, chat_id, *, direction: str | None, chat_name: str, is_group) -> tuple | None:
    """One archive row from EITHER shape this system speaks: an inbox item (`from`/`body`/`ts`/`messageId`/
    `isGroup`/`group`) or a thread message (`who`/`body`/`ts`/`dir`/`id`). Empty bodies are not archived —
    a media-only row still lands, carrying its media_type."""
    body = str(m.get("body") or "").strip()
    media = str(m.get("mediaType") or "")
    if not body and not media:
        return None
    try:
        ts = float(m.get("ts") or m.get("timestamp") or time.time())
    except (TypeError, ValueError):
        ts = time.time()
    d = direction or ("out" if m.get("dir") == "out" else "in")
    sender = str(m.get("from") or m.get("who") or m.get("senderName") or "")
    name = str(chat_name or m.get("group") or "")
    grp = bool(is_group) if is_group is not None else bool(m.get("isGroup"))
    return (str(platform), str(chat_id), name, 1 if grp else 0, sender, d, ts, body, media,
            _msg_id(m, platform, chat_id, ts, body))


def record(platform: str, chat_id, msgs: list[dict], *, direction: str | None = None,
           chat_name: str = "", is_group=None) -> int:
    """Append messages of one chat. Idempotent by (platform, chat_id, msg_id) — a connector retry, a
    re-fetch of the same window or a thread echo inserts nothing twice. Returns how many rows are new."""
    if not msgs:
        return 0
    try:
        rows = [r for r in (_norm(m, platform, chat_id, direction=direction, chat_name=chat_name,
                                  is_group=is_group) for m in msgs if isinstance(m, dict)) if r]
        if not rows:
            return 0
        with _LOCK:
            conn = _conn()
            with conn:
                # NOT total_changes: the FTS trigger fires per new row and doubles that count. rowcount
                # counts only the statement's own inserts, and OR IGNORE keeps skipped rows out of it.
                cur = conn.executemany(
                    "INSERT OR IGNORE INTO messages"
                    " (platform, chat_id, chat_name, is_group, sender, direction, ts, body, media_type, msg_id)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
                return max(0, cur.rowcount)
    except Exception:  # noqa: BLE001 — the archive must never break the store that feeds it
        return 0


def record_items(items: list[dict]) -> int:
    """The inbound-triage seam: inbox items carry their platform/chat per item."""
    n = 0
    for it in items or []:
        if isinstance(it, dict):
            n += record(str(it.get("platform") or "?"), it.get("chatId") or "?", [it], direction="in")
    return n


def search(q: str | None = None, *, sender: str | None = None, chat: str | None = None,
           platform: str | None = None, since: float | None = None, until: float | None = None,
           direction: str | None = None, limit: int = 20) -> list[dict]:
    """The catalogued lookup the platforms never gave us. `q` walks the FTS index; every other argument is a
    structured filter (sender/chat match by substring, case-insensitive — the operator says «the school», not
    an exact display name). Newest first."""
    try:
        conn = _conn()
        where, args = [], []
        if q and str(q).strip():
            fts = " ".join('"' + t.replace('"', "") + '"' for t in str(q).split())
            where.append("m.id IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?)")
            args.append(fts)
        for field, val in (("sender", sender), ("chat_name", chat)):
            if val and str(val).strip():
                where.append(f"m.{field} LIKE ? COLLATE NOCASE")
                args.append(f"%{val}%")
        if platform:
            where.append("m.platform = ?"); args.append(str(platform))
        if direction in ("in", "out"):
            where.append("m.direction = ?"); args.append(direction)
        if since is not None:
            where.append("m.ts >= ?"); args.append(float(since))
        if until is not None:
            where.append("m.ts <= ?"); args.append(float(until))
        sql = "SELECT m.* FROM messages m"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY m.ts DESC LIMIT ?"
        args.append(max(1, min(int(limit or 20), 200)))
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    except Exception:  # noqa: BLE001
        return []


def replied(platform: str, chat_id, after_ts: float) -> dict | None:
    """«Did we ever answer it?» — the first OUT row in that chat after the instant. A JOIN, not a memory."""
    try:
        row = _conn().execute(
            "SELECT * FROM messages WHERE platform=? AND chat_id=? AND direction='out' AND ts>? "
            "ORDER BY ts LIMIT 1", (str(platform), str(chat_id), float(after_ts))).fetchone()
        return dict(row) if row else None
    except Exception:  # noqa: BLE001
        return None


def stats() -> dict:
    """Row count and time span — the health line a brief or a doctor can print."""
    try:
        r = _conn().execute("SELECT COUNT(*) n, MIN(ts) lo, MAX(ts) hi FROM messages").fetchone()
        return {"messages": r["n"], "oldest": r["lo"], "newest": r["hi"]}
    except Exception:  # noqa: BLE001
        return {"messages": 0, "oldest": None, "newest": None}
