"""bus/log.py — DURABLE Nervous System event log (V2-001).

Every event that passes through the bus is persisted into an SQLite `events` table. It goes to the SAME `zaelar.db`
file as central memory (V2-002) — one local file, no server or broker (`zaelar-memory.md` design principle). Since
`memory/` does not exist yet when V2-001 is built, this module resolves the path itself (`db_path()`) and lazily
creates the file/tables; V2-002 will reuse that same path (`ZAELAR_DB` / `memory/_data/zaelar.db`).

It attaches as a **SYNCHRONOUS** bus sink (`bus.add_sink`): the bus calls `_write(rec)` on the publishing thread
(loop-agnostic). It uses its own SQLite connection with `check_same_thread=False` + a `threading.Lock`, and WAL so
readers do not block. The log is best-effort: a write failure NEVER breaks event dispatch (the bus sink is already
protected by try/except).
"""
import json
import os
import queue
import sqlite3
import threading
import time
from pathlib import Path

from nucleo import workspace as _workspace

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()
_attached = False


def db_path() -> Path:
    """Shared SQLite file path. Overridden by `ZAELAR_DB` (power-user/headless/tests); defaults to
    `<workspace>/memory/_data/zaelar.db` (gitignored) — without `ZAELAR_WORKSPACE` this is BYTE-IDENTICAL to the old
    path. The directory is created lazily. SAME file as `memory/db.py`."""
    env = os.getenv("ZAELAR_DB")
    if env:
        return Path(env)
    return _workspace.root() / "memory" / "_data" / "zaelar.db"


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_ms   REAL    NOT NULL,
            topic   TEXT    NOT NULL,
            payload TEXT               -- JSON of the payload (or repr if it cannot be serialized)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_topic ON events(topic)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts_ms)")
    _migrate_columns(conn)
    conn.commit()
    _conn = conn
    return conn


# ANALYSIS COLUMNS (2026-08-09). Until now an event was `(ts, topic, payload-JSON)`: to answer "give me the whole
# flow for 'show me the weather in Soria'" or "what did this user do in Tuesday's session?", we had to scan and
# parse ALL JSON. These fields are PROMOTED from payload to indexed columns — the full JSON is still stored intact
# (it is the source of truth; this is a query projection).
#
# Added with idempotent ALTER TABLE instead of recreating the table: a live installation cannot lose its history to
# a migration, and SQLite adds NULL columns without rewriting the file. Old rows keep NULL — correct and honest:
# that data did not exist when they were recorded.
_COLUMNS = (
    ("corr_id", "TEXT"),      # CORRELATION ID = the complete flow from start to finish (voice/trace.py)
    ("session_id", "TEXT"),   # operator work session (observability/identity.py)
    ("user_id", "TEXT"),      # installation / account
    ("cat", "TEXT"),          # family: flash · worker · memory · widget · system · pulse
    ("kind", "TEXT"),         # specific type within the family
    ("label", "TEXT"),        # what happened, in one line
    ("span", "TEXT"),         # ACTOR within the flow: worker:5 · rail:music · web:t2
    ("ms", "REAL"),           # REAL operation duration, when the event carries it
    ("model", "TEXT"),        # model that served the turn/step
    ("tokens_in", "INTEGER"),
    ("tokens_out", "INTEGER"),
    ("ver", "TEXT"),          # code version that generated it (V2-074)
)


def _migrate_columns(conn: sqlite3.Connection) -> None:
    """Add missing columns. Idempotent and non-destructive: can be called on every boot."""
    try:
        have = {r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()}
    except Exception:
        return
    for name, decl in _COLUMNS:
        if name in have:
            continue
        try:
            conn.execute(f"ALTER TABLE events ADD COLUMN {name} {decl}")
        except Exception:
            pass
    for col in ("corr_id", "session_id", "user_id", "cat"):
        try:
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_events_{col} ON events({col})")
        except Exception:
            pass


# `ms` has no single name: each site stamps its own (brain_ms, tts_ms, gen_ms…). Same preference order the viewer
# uses — a TOTAL duration beats a partial one (`ttft_ms` = first token only).
_MS_FIELDS = ("brain_ms", "fast_ms", "deep_ms", "tts_ms", "stt_ms", "gen_ms",
              "architect_ms", "cluster_ms", "triage_ms", "mem_ms", "ttft_ms")


def _columns_from(payload) -> tuple:
    """Project an event payload to the column tuple. Tolerant: missing values stay NULL."""
    if not isinstance(payload, dict):
        return (None,) * len(_COLUMNS)
    ms = None
    for f in _MS_FIELDS:
        v = payload.get(f)
        if isinstance(v, (int, float)):
            ms = float(v)
            break

    def _s(key, cap=200):
        v = payload.get(key)
        return str(v)[:cap] if v not in (None, "") else None

    def _i(key):
        v = payload.get(key)
        return int(v) if isinstance(v, (int, float)) else None

    return (_s("trace", 64), _s("sid", 64), _s("uid", 64), _s("cat", 24), _s("kind", 40),
            _s("label", 200), _s("span", 64), ms, _s("model", 120),
            _i("prompt_tokens"), _i("completion_tokens"), _s("ver", 40))


# OFF-THREAD WRITE (2026-08-09). The sink is called by the bus ON THE PUBLISHING THREAD — and that thread is often
# the voice thread. One synchronous INSERT per event there is exactly the failure V2-035 pulled out of the observer:
# synchronous writes held the GIL during event bursts and choked the TTS audio pump (choppy voice). That is why the
# durable log had been OFF by default since V2-001 "to avoid touching the hot path".
#
# The solution is not to leave it off — without it there is nothing to analyze — but for the sink to only ENQUEUE
# (microsecond operation that never blocks) and a dedicated thread to drain in order. BOUNDED queue: under a burst,
# log events are dropped before slowing voice. That is the correct priority.
_q: "queue.Queue" = queue.Queue(maxsize=20000)
_dropped = {"n": 0}


def _writer_loop():
    while True:
        rec = _q.get()
        try:
            if rec is not None:
                _write_now(rec)
        except Exception:
            pass
        finally:
            _q.task_done()      # enables Queue.join() — tests wait for draining before reading


_writer_thread = threading.Thread(target=_writer_loop, name="bus-log-writer", daemon=True)
_writer_thread.start()


def drain(timeout: float = 2.0) -> None:
    """Wait for the queue to empty. For tests and orderly shutdown; never called on the hot path."""
    import time as _t
    t0 = _t.time()
    while not _q.empty() and (_t.time() - t0) < timeout:
        _t.sleep(0.01)


# WHAT DESERVES PERSISTENCE (the question V2-001 left open when putting the log on standby). The HEARTBEAT does not:
# the orchestrator loop ticks at ~1 Hz, so `loop.tick` and its `kind="pulse"` reflection would insert ~140,000 rows
# per day for an event carrying no data — drowning what matters and eating the whole retention window. The heartbeat
# exists for the live UI (the orb ECG), which receives it by SSE anyway; it adds nothing to the RECORD. Any other
# topic is stored: when in doubt, record it.
_SKIP_TOPICS = {"loop.tick"}
_SKIP_KINDS = {"pulse"}


def _worth_persisting(rec: dict) -> bool:
    if str(rec.get("topic") or "") in _SKIP_TOPICS:
        return False
    p = rec.get("payload")
    return not (isinstance(p, dict) and p.get("kind") in _SKIP_KINDS)


def _write(rec: dict):
    """Bus sink: ENQUEUE the event. Never blocks the publisher (see the note above)."""
    if not _worth_persisting(rec):
        return
    try:
        _q.put_nowait(rec)
    except queue.Full:
        _dropped["n"] += 1      # visible in `stats()`: better to lose log than slow voice


def _write_now(rec: dict):
    """Real persistence, on the writer thread. `rec` = {topic, ts_ms, payload}. Best-effort."""
    try:
        payload = rec.get("payload")
        try:
            blob = json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            blob = json.dumps(str(payload), ensure_ascii=False)
        cols = _columns_from(payload)
        names = ", ".join(c[0] for c in _COLUMNS)
        marks = ", ".join("?" for _ in _COLUMNS)
        with _lock:
            conn = _connect()
            conn.execute(
                f"INSERT INTO events (ts_ms, topic, payload, {names}) VALUES (?, ?, ?, {marks})",
                (float(rec.get("ts_ms") or time.time() * 1000.0), str(rec.get("topic") or ""), blob, *cols),
            )
            conn.commit()
    except Exception:
        pass


# RETENTION (2026-08-09). The other reason the durable log was off: "unbounded zaelar.db growth". With the log on,
# this stops being hypothetical — an active session generates thousands of rows per day — and now it is also the
# ONLY place where events live. Prune by age and with a hard row cap, both configurable. Runs when attaching the
# sink (boot) on the writer thread: never on the voice thread.
_RETENTION_DAYS = float(os.getenv("ZAELAR_EVENTS_RETENTION_DAYS", "30"))
_MAX_ROWS = int(os.getenv("ZAELAR_EVENTS_MAX_ROWS", "500000"))


def prune() -> int:
    """Delete old rows and anything past the cap. Returns how many rows went away. Best-effort: a pruning failure
    can NEVER prevent events from continuing to be recorded."""
    gone = 0
    try:
        with _lock:
            conn = _connect()
            if _RETENTION_DAYS > 0:
                cutoff = (time.time() - _RETENTION_DAYS * 86400) * 1000.0
                gone += conn.execute("DELETE FROM events WHERE ts_ms < ?", (cutoff,)).rowcount or 0
            if _MAX_ROWS > 0:
                # By id (autoincremental), not ts_ms: this is the real insertion order and uses the PK.
                row = conn.execute(
                    "SELECT id FROM events ORDER BY id DESC LIMIT 1 OFFSET ?", (_MAX_ROWS,)).fetchone()
                if row:
                    gone += conn.execute("DELETE FROM events WHERE id <= ?", (row[0],)).rowcount or 0
            conn.commit()
    except Exception:
        pass
    return gone


def stats() -> dict:
    """Health of the log itself: how much exists, how much was dropped due to saturation, and how much remains queued."""
    return {"rows": count(), "dropped": _dropped["n"], "queued": _q.qsize()}


def attach(bus_mod=None):
    """Attach the log to the bus (idempotent). Called from the server lifespan (T40)."""
    global _attached
    if _attached:
        return
    if bus_mod is None:
        import bus as bus_mod  # noqa
    bus_mod.add_sink(_write)
    _attached = True
    # Prune at boot, on its own thread: with 500k rows DELETE can take time and must not delay boot.
    threading.Thread(target=prune, name="bus-log-prune", daemon=True).start()


def detach(bus_mod=None):
    global _attached
    if bus_mod is None:
        import bus as bus_mod  # noqa
    bus_mod.remove_sink(_write)
    _attached = False


# ── reads (for future /debug, tests, and the memory retriever) ──────────────────────────────────────────
def recent(limit: int = 100, topic: str = "") -> list[dict]:
    """Latest events (newest first). Optional filter by exact topic or prefix ending with `*`."""
    with _lock:
        conn = _connect()
        if topic.endswith("*"):
            rows = conn.execute(
                "SELECT id, ts_ms, topic, payload FROM events WHERE topic LIKE ? ORDER BY id DESC LIMIT ?",
                (topic[:-1] + "%", limit),
            ).fetchall()
        elif topic:
            rows = conn.execute(
                "SELECT id, ts_ms, topic, payload FROM events WHERE topic = ? ORDER BY id DESC LIMIT ?",
                (topic, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, ts_ms, topic, payload FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    out = []
    for r in rows:
        try:
            payload = json.loads(r[3]) if r[3] is not None else None
        except Exception:
            payload = r[3]
        out.append({"id": r[0], "ts_ms": r[1], "topic": r[2], "payload": payload})
    return out


def count(topic: str = "") -> int:
    with _lock:
        conn = _connect()
        if topic:
            return conn.execute("SELECT COUNT(*) FROM events WHERE topic = ?", (topic,)).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]


def close():
    """Close the connection (tests / shutdown). Idempotent."""
    global _conn
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None
