"""memory/db.py — SQLite connection for central memory (V2-002).

A **single file** `zaelar.db` (WAL) shared with the durable bus log (`bus/log.py` uses the same path). No server or
broker. This module:

  - resolves the path (`db_path()`, `ZAELAR_DB` override; default `memory/_data/zaelar.db`, gitignored),
  - opens the connection in **WAL** (`synchronous=NORMAL`) so reads can happen while writes happen,
  - loads the **sqlite-vec** extension (best-effort -> `Database.vec_available`; if missing, memory degrades to
    FTS/keyword-only search without breaking),
  - creates the schema (`memory/schema.py`) idempotently and tracks the version in `PRAGMA user_version`.

**Concurrency**: zaelar is one process with two loops (uvicorn + LiveKit job-thread). The ONLY writer is the queue
(`memory/writer.py`); readers (retriever/state) go direct. We share ONE connection (`check_same_thread=False`)
serialized by a `threading.RLock`: at our scale (one user, tens of thousands of memories) hold times are sub-ms, and
it avoids traps from sharing a `sqlite3.Connection` across threads. WAL also lets a future reader/writer split avoid
schema changes.
"""
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from . import schema as _schema
from nucleo import workspace as _workspace


def db_path() -> Path:
    """Shared SQLite file path. Override with `ZAELAR_DB` (power-user/headless/tests); default
    `<workspace>/memory/_data/zaelar.db` (gitignored) — `<workspace>` is the repo root unless `ZAELAR_WORKSPACE`
    points to a mounted volume (Phase 3, real paid accounts) — without that env var this is BYTE-IDENTICAL to the
    previous path. Directory is created lazily. SAME path as `bus/log.py`."""
    env = os.getenv("ZAELAR_DB")
    if env:
        return Path(env)
    return _workspace.root() / "memory" / "_data" / "zaelar.db"


def _try_load_vec(conn: sqlite3.Connection) -> bool:
    """Load the sqlite-vec extension into the connection. Best-effort -> returns whether it is available."""
    try:
        import sqlite_vec  # noqa
    except Exception:
        return False
    try:
        conn.enable_load_extension(True)
    except (AttributeError, sqlite3.OperationalError):
        return False
    try:
        sqlite_vec.load(conn)
        conn.execute("SELECT vec_version()").fetchone()
        return True
    except Exception:
        return False
    finally:
        try:
            conn.enable_load_extension(False)
        except Exception:
            pass


def _has_fts5(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE IF EXISTS _fts5_probe")
        return True
    except sqlite3.OperationalError:
        return False


class Database:
    """Wrapper around the `zaelar.db` connection. Usually the `get_db()` singleton is used."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # SQLite `lower()` is ASCII-ONLY, so accented uppercase letters do NOT match Python `.lower()`. Any
        # case-insensitive comparison over names with accents/Spanish enye would silently fail. `pylower` applies
        # Python Unicode semantics in SQL so both sides match.
        try:
            self.conn.create_function(
                "pylower", 1, lambda s: s.lower() if isinstance(s, str) else s, deterministic=True)
        except Exception:
            pass
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass
        self.vec_available = _try_load_vec(self.conn)
        self.fts_available = _has_fts5(self.conn)
        self._migrate()

    # ── migrations / schema ──────────────────────────────────────────────────────────────────────────────
    def _migrate(self):
        with self._lock:
            cur = self.conn.execute("PRAGMA user_version").fetchone()
            version = cur[0] if cur else 0
            for stmt in _schema.BASE_DDL:
                self.conn.execute(stmt)
            if self.vec_available:
                # provider-driven dim (V2-031): vec table is created with the ACTIVE embedding dim (embeddinggemma
                # 768 / bge-m3·e5-large 1024...). IF NOT EXISTS preserves the existing one -> a model change requires
                # `memory/reembed.py` (drop+recreate), flagged by `reembed.check()` at startup. Lazy import.
                from . import embeddings as _emb
                self.conn.execute(_schema.vec_memories_ddl(_emb.dim()))
            if self.fts_available:
                self.conn.execute(_schema.FTS_MEMORIES)
            # v1->v2 (V2-013): memory is a PILL — add `slot`/`meta` if missing (idempotent, non-destructive ALTER;
            # SQLite has no ADD COLUMN IF NOT EXISTS -> inspect existing columns first).
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(memories)").fetchall()}
            for name, stmt in _schema.MEMORIES_V2_COLUMNS:
                if name not in cols:
                    self.conn.execute(stmt)
            for stmt in _schema.MEMORIES_V2_INDEXES:   # indexes depending on v2 columns (after ALTER)
                self.conn.execute(stmt)
            if version < _schema.SCHEMA_VERSION:
                self.conn.execute(f"PRAGMA user_version={_schema.SCHEMA_VERSION}")
            self.conn.commit()

    def schema_version(self) -> int:
        with self._lock:
            return self.conn.execute("PRAGMA user_version").fetchone()[0]

    def tables(self) -> set[str]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            ).fetchall()
        return {r[0] for r in rows}

    # ── serialized access ────────────────────────────────────────────────────────────────────────────────
    @contextmanager
    def cursor(self):
        """Cursor under the lock. Commits on clean exit, rolls back on exception."""
        with self._lock:
            cur = self.conn.cursor()
            try:
                yield cur
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                cur.close()

    def execute(self, sql: str, params: tuple | list = ()):  # simple write with commit
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.lastrowid

    def query(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(sql, params).fetchone()

    def close(self):
        with self._lock:
            try:
                self.conn.close()
            except Exception:
                pass


# ── module singleton ────────────────────────────────────────────────────────────────────────────────────
_DB: Database | None = None
# RLock, not Lock (2026-08-16): on a fresh DB, Database.__init__ -> _migrate() -> embeddings.dim() ->
# _resolve_backend() -> _ollama_embed() logs perf via voice.observer.perf(), which walks emit() ->
# stamp_identity() -> nucleo.runstate.stopped() -> kv_get() -> get_db() again, on the SAME thread, before
# the first get_db() call has returned. A plain Lock self-deadlocks there every time; RLock does not.
_DB_LOCK = threading.RLock()


def get_db() -> Database:
    global _DB
    with _DB_LOCK:
        if _DB is None:
            _DB = Database()
        return _DB


def reset_db():
    """Close the singleton (tests / ZAELAR_DB change). The next `get_db()` reopens it."""
    global _DB
    with _DB_LOCK:
        if _DB is not None:
            _DB.close()
            _DB = None
