# History backfill: which chats have been walked back to their beginning, and the anchors the walk needs.
import logging
import time


def oldest(platform: str, chat_id) -> dict | None:
    """The OLDEST message held of one chat — the anchor a backfill asks the platform to go back from."""
    try:
        row = _svc._conn().execute("SELECT msg_id, direction, ts FROM messages WHERE platform=? AND chat_id=? "
                                   "ORDER BY ts LIMIT 1", (str(platform), str(chat_id))).fetchone()
        return dict(row) if row else None
    except Exception as e:  # noqa: BLE001
        logging.getLogger("zaelar.messaging.archive").warning(f"archive oldest unreadable: {type(e).__name__}")
        return None


def count(platform: str, chat_id) -> int:
    try:
        return int(_svc._conn().execute("SELECT COUNT(*) FROM messages WHERE platform=? AND chat_id=?",
                                        (str(platform), str(chat_id))).fetchone()[0])
    except Exception as e:  # noqa: BLE001 — an unreadable count reads as nothing held
        logging.getLogger("zaelar.messaging.archive").warning(f"archive count unreadable: {type(e).__name__}")
        return 0


def backfill_state(platform: str, chat_id) -> dict:
    try:
        row = _svc._conn().execute("SELECT done, pages, updated FROM backfill WHERE platform=? AND chat_id=?",
                                   (str(platform), str(chat_id))).fetchone()
        return dict(row) if row else {"done": 0, "pages": 0, "updated": 0.0}
    except Exception:  # noqa: BLE001 — unknown state reads as «not walked yet»
        return {"done": 0, "pages": 0, "updated": 0.0}


def backfill_mark(platform: str, chat_id, *, done: bool | None = None, page: bool = False) -> None:
    """Record progress on one chat's walk back: one more page arrived, or the walk is over."""
    try:
        with _svc._LOCK:
            conn = _svc._conn()
            with conn:
                conn.execute("INSERT OR IGNORE INTO backfill(platform, chat_id, updated) VALUES (?,?,?)",
                             (str(platform), str(chat_id), time.time()))
                conn.execute("UPDATE backfill SET pages=pages+?, done=COALESCE(?, done), updated=? "
                             "WHERE platform=? AND chat_id=?",
                             (1 if page else 0, None if done is None else (1 if done else 0), time.time(),
                              str(platform), str(chat_id)))
    except Exception as e:  # noqa: BLE001
        logging.getLogger("zaelar.messaging.archive").warning(f"backfill state not saved: {type(e).__name__}")


def backfill_stats(platform: str) -> dict:
    """How far the walk back has gone: chats finished, chats started, messages held."""
    try:
        c = _svc._conn()
        done = c.execute("SELECT COUNT(*) FROM backfill WHERE platform=? AND done=1", (platform,)).fetchone()[0]
        started = c.execute("SELECT COUNT(*) FROM backfill WHERE platform=?", (platform,)).fetchone()[0]
        msgs = c.execute("SELECT COUNT(*) FROM messages WHERE platform=?", (platform,)).fetchone()[0]
        return {"done": int(done), "started": int(started), "messages": int(msgs)}
    except Exception:  # noqa: BLE001 — a stats line never breaks its caller
        return {"done": 0, "started": 0, "messages": 0}


# Read back through the facade (V2-778 F1): tests patch `_db_path`/`_conn` there.
from connectors.messaging import archive as _svc  # noqa: E402
