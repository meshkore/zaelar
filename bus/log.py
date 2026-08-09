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
    _migrate_columns(conn)
    conn.commit()
    _conn = conn
    return conn


# COLUMNAS DE ANÁLISIS (2026-08-09). Hasta aquí un evento era `(ts, topic, payload-JSON)`: para responder «dame
# todo el flujo de "enséñame el tiempo en Soria"» o «¿qué hizo este usuario en la sesión del martes?» había que
# escanear y parsear TODO el JSON. Estos campos SUBEN del payload a columnas indexadas — el JSON completo se
# sigue guardando intacto (es la fuente de verdad; esto es una proyección para consultar).
#
# Se añaden con ALTER TABLE idempotente en vez de recrear la tabla: una instalación viva no puede perder su
# histórico por una migración, y SQLite añade columnas NULL sin reescribir el fichero. Las filas antiguas quedan
# con NULL — correcto y honesto: ese dato no existía cuando se registraron.
_COLUMNS = (
    ("corr_id", "TEXT"),      # CORRELATION ID = el flujo completo de inicio a fin (voice/trace.py)
    ("session_id", "TEXT"),   # sesión de trabajo del operador (observability/identity.py)
    ("user_id", "TEXT"),      # instalación / cuenta
    ("cat", "TEXT"),          # familia: flash · worker · memory · widget · system · pulse
    ("kind", "TEXT"),         # tipo concreto dentro de la familia
    ("label", "TEXT"),        # qué pasó, en una línea
    ("span", "TEXT"),         # ACTOR dentro del flujo: worker:5 · rail:music · web:t2
    ("ms", "REAL"),           # duración REAL de la operación, cuando el evento la trae
    ("model", "TEXT"),        # modelo que sirvió el turno/paso
    ("tokens_in", "INTEGER"),
    ("tokens_out", "INTEGER"),
    ("ver", "TEXT"),          # versión del código que lo generó (V2-074)
)


def _migrate_columns(conn: sqlite3.Connection) -> None:
    """Añade las columnas que falten. Idempotente y no destructivo: se puede llamar en cada arranque."""
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


# `ms` no tiene un nombre único: cada sitio estampa el suyo (brain_ms, tts_ms, gen_ms…). Mismo orden de
# preferencia que usa el visor — una duración TOTAL gana a una parcial (`ttft_ms` = solo el primer token).
_MS_FIELDS = ("brain_ms", "fast_ms", "deep_ms", "tts_ms", "stt_ms", "gen_ms",
              "architect_ms", "cluster_ms", "triage_ms", "mem_ms", "ttft_ms")


def _columns_from(payload) -> tuple:
    """Proyecta un payload de evento a la tupla de columnas. Tolerante: lo que no venga queda a NULL."""
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


# ESCRITURA OFF-THREAD (2026-08-09). El sink lo llama el bus EN EL HILO QUE PUBLICA — y ese hilo es, muchas
# veces, el de la voz. Un INSERT síncrono por evento ahí es exactamente el fallo que V2-035 sacó del observador:
# las escrituras síncronas retenían el GIL en ráfagas de eventos y ahogaban el pump de audio del TTS (voz
# entrecortada). Por eso el log durable llevaba desde V2-001 APAGADO por defecto «para no tocar el hot path».
#
# La solución no es dejarlo apagado —sin él no hay nada que analizar— sino que el sink solo ENCOLE (operación de
# microsegundos que nunca bloquea) y un hilo dedicado drene en orden. Cola ACOTADA: bajo una ráfaga se pierden
# eventos de log antes que ralentizar la voz. Esa es la prioridad correcta.
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
            _q.task_done()      # permite Queue.join() — los tests esperan el drenado antes de leer


_writer_thread = threading.Thread(target=_writer_loop, name="bus-log-writer", daemon=True)
_writer_thread.start()


def drain(timeout: float = 2.0) -> None:
    """Espera a que la cola se vacíe. Para tests y para el apagado ordenado; nunca se llama en el hot path."""
    import time as _t
    t0 = _t.time()
    while not _q.empty() and (_t.time() - t0) < timeout:
        _t.sleep(0.01)


# QUÉ MERECE PERSISTIRSE (la pregunta que V2-001 dejó abierta al poner el log en standby). El LATIDO no: el
# loop orquestador tiquea a ~1 Hz, así que `loop.tick` y su reflejo `kind="pulse"` meterían ~140.000 filas al día
# de un evento que no lleva ningún dato — ahogando lo que sí importa y comiéndose la retención entera. El latido
# existe para la UI en vivo (el ECG del orbe), que lo recibe por SSE igual; para el REGISTRO no aporta nada.
# Cualquier otro topic sí se guarda: ante la duda, se registra.
_SKIP_TOPICS = {"loop.tick"}
_SKIP_KINDS = {"pulse"}


def _worth_persisting(rec: dict) -> bool:
    if str(rec.get("topic") or "") in _SKIP_TOPICS:
        return False
    p = rec.get("payload")
    return not (isinstance(p, dict) and p.get("kind") in _SKIP_KINDS)


def _write(rec: dict):
    """Sink del bus: ENCOLA el evento. Nunca bloquea al que publica (ver la nota de arriba)."""
    if not _worth_persisting(rec):
        return
    try:
        _q.put_nowait(rec)
    except queue.Full:
        _dropped["n"] += 1      # visible en `stats()`: mejor perder log que frenar la voz


def _write_now(rec: dict):
    """Persistencia real, en el hilo del writer. `rec` = {topic, ts_ms, payload}. Best-effort."""
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


# RETENCIÓN (2026-08-09). La otra razón por la que el log durable estaba apagado: «crecimiento sin límite de
# zaelar.db». Con el log encendido esto deja de ser hipotético — una sesión activa genera miles de filas al día —
# y ahora además es el ÚNICO sitio donde viven los eventos. Se poda por antigüedad y con un techo duro de filas,
# ambos configurables. Corre al enganchar el sink (arranque) en el hilo del writer: nunca en el de la voz.
_RETENTION_DAYS = float(os.getenv("ZAELAR_EVENTS_RETENTION_DAYS", "30"))
_MAX_ROWS = int(os.getenv("ZAELAR_EVENTS_MAX_ROWS", "500000"))


def prune() -> int:
    """Borra lo viejo y lo que pase del techo. Devuelve cuántas filas se fueron. Best-effort: un fallo podando
    NUNCA puede impedir que se sigan registrando eventos."""
    gone = 0
    try:
        with _lock:
            conn = _connect()
            if _RETENTION_DAYS > 0:
                cutoff = (time.time() - _RETENTION_DAYS * 86400) * 1000.0
                gone += conn.execute("DELETE FROM events WHERE ts_ms < ?", (cutoff,)).rowcount or 0
            if _MAX_ROWS > 0:
                # Por id (autoincremental) y no por ts_ms: es el orden real de inserción y usa la PK.
                row = conn.execute(
                    "SELECT id FROM events ORDER BY id DESC LIMIT 1 OFFSET ?", (_MAX_ROWS,)).fetchone()
                if row:
                    gone += conn.execute("DELETE FROM events WHERE id <= ?", (row[0],)).rowcount or 0
            conn.commit()
    except Exception:
        pass
    return gone


def stats() -> dict:
    """Salud del propio log: cuánto hay, cuánto se ha descartado por saturación y cuánto queda en cola."""
    return {"rows": count(), "dropped": _dropped["n"], "queued": _q.qsize()}


def attach(bus_mod=None):
    """Engancha el log al bus (idempotente). Llamado desde el lifespan del server (T40)."""
    global _attached
    if _attached:
        return
    if bus_mod is None:
        import bus as bus_mod  # noqa
    bus_mod.add_sink(_write)
    _attached = True
    # Poda al arrancar, en su propio hilo: con 500k filas el DELETE puede tardar y no puede retrasar el boot.
    threading.Thread(target=prune, name="bus-log-prune", daemon=True).start()


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
