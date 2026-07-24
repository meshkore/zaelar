"""bus/log.py — log DURABLE de eventos del Sistema Nervioso (V2-001).

Cada evento que pasa por el bus se persiste en una tabla `events` de SQLite. Va al MISMO fichero
`zaelar.db` de la memoria central (V2-002) — un solo fichero local, sin servidor ni broker (principio
de diseño de `zaelar-memory.md`). Como `memory/` aún no existe cuando se construye V2-001, este módulo
resuelve la ruta él mismo (`db_path()`) y crea el fichero/tablas de forma perezosa; V2-002 reutilizará
esa misma ruta (`ZAELAR_DB` / `memory/_data/zaelar.db`).

Se engancha como un **sink SÍNCRONO** del bus (`bus.add_sink`): el bus llama a `_write(rec)` en el hilo
que publica (loop-agnóstico). Usa una conexión SQLite propia con `check_same_thread=False` + un
`threading.Lock`, y WAL para que los lectores no se bloqueen. El log es best-effort: un fallo de escritura
NUNCA revienta el reparto de eventos (el sink del bus ya está protegido por try/except).
"""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

from nucleo import workspace as _workspace

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()
_attached = False


def db_path() -> Path:
    """Ruta del fichero SQLite compartido. Override por `ZAELAR_DB` (power-user/headless/tests); por defecto
    `<workspace>/memory/_data/zaelar.db` (gitignored) — sin `ZAELAR_WORKSPACE` esto es BYTE IDÉNTICO a
    la ruta de siempre. El directorio se crea perezosamente. MISMO fichero que `memory/db.py`."""
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
            payload TEXT               -- JSON del payload (o repr si no serializa)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_topic ON events(topic)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts_ms)")
    conn.commit()
    _conn = conn
    return conn


def _write(rec: dict):
    """Sink del bus: persiste un evento. `rec` = {topic, ts_ms, payload}. Best-effort."""
    try:
        payload = rec.get("payload")
        try:
            blob = json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            blob = json.dumps(str(payload), ensure_ascii=False)
        with _lock:
            conn = _connect()
            conn.execute(
                "INSERT INTO events (ts_ms, topic, payload) VALUES (?, ?, ?)",
                (float(rec.get("ts_ms") or time.time() * 1000.0), str(rec.get("topic") or ""), blob),
            )
            conn.commit()
    except Exception:
        pass


def attach(bus_mod=None):
    """Engancha el log al bus (idempotente). Llamado desde el lifespan del server (T40)."""
    global _attached
    if _attached:
        return
    if bus_mod is None:
        import bus as bus_mod  # noqa
    bus_mod.add_sink(_write)
    _attached = True


def detach(bus_mod=None):
    global _attached
    if bus_mod is None:
        import bus as bus_mod  # noqa
    bus_mod.remove_sink(_write)
    _attached = False


# ── lectura (para /debug futuro, tests, y el retriever de memoria) ─────────────────────────────────────
def recent(limit: int = 100, topic: str = "") -> list[dict]:
    """Últimos eventos (más nuevos primero). Filtro opcional por topic exacto o prefijo con `*` al final."""
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
    """Cierra la conexión (tests / shutdown). Idempotente."""
    global _conn
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None
