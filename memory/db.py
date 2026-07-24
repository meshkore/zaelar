"""memory/db.py — conexión SQLite de la memoria central (V2-002).

Un **solo fichero** `zaelar.db` (WAL) compartido con el log durable del bus (`bus/log.py` usa el mismo path).
Sin servidor ni broker. Este módulo:

  - resuelve la ruta (`db_path()`, override `ZAELAR_DB`; por defecto `memory/_data/zaelar.db`, gitignored),
  - abre la conexión en **WAL** (`synchronous=NORMAL`) para leer mientras se escribe,
  - carga la extensión **sqlite-vec** (best-effort → `Database.vec_available`; si falta, la memoria degrada a
    búsqueda solo-FTS/keyword sin romperse),
  - crea el schema (`memory/schema.py`) de forma idempotente y lleva la versión en `PRAGMA user_version`.

**Concurrencia**: zaelar es un solo proceso con dos loops (uvicorn + job-thread de LiveKit). El ÚNICO escritor
es la cola (`memory/writer.py`); los lectores (retriever/state) van directos. Compartimos UNA conexión
(`check_same_thread=False`) serializada por un `threading.RLock`: a nuestra escala (un usuario, decenas de
miles de recuerdos) los hold-times son sub-ms, y evita las trampas de compartir un `sqlite3.Connection` entre
hilos. WAL permite además que un futuro split lector/escritor no requiera cambios de schema.
"""
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from . import schema as _schema
from nucleo import workspace as _workspace


def db_path() -> Path:
    """Ruta del fichero SQLite compartido. Override por `ZAELAR_DB` (power-user/headless/tests); por defecto
    `<workspace>/memory/_data/zaelar.db` (gitignored) — `<workspace>` es la raíz del repo salvo que
    `ZAELAR_WORKSPACE` apunte a un volumen montado (Fase 3, cuentas de pago reales) — sin esa env var
    esto es BYTE IDÉNTICO a la ruta de siempre. El directorio se crea perezosamente. MISMO path que
    `bus/log.py`."""
    env = os.getenv("ZAELAR_DB")
    if env:
        return Path(env)
    return _workspace.root() / "memory" / "_data" / "zaelar.db"


def _try_load_vec(conn: sqlite3.Connection) -> bool:
    """Carga la extensión sqlite-vec en la conexión. Best-effort → devuelve si está disponible."""
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
    """Envoltorio de la conexión a `zaelar.db`. Normalmente se usa el singleton `get_db()`."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # `lower()` de SQLite es SOLO-ASCII → `lower('Álvaro')` deja la Á y NO casa con el `.lower()` de Python
        # ('álvaro'). Toda comparación case-insensitive sobre nombres con tilde/ñ (entidades: Álvaro, María, mamá…)
        # fallaría en silencio. `pylower` aplica la semántica Unicode de Python en SQL para que ambos lados casen.
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

    # ── migraciones / schema ─────────────────────────────────────────────────────────────────────────────
    def _migrate(self):
        with self._lock:
            cur = self.conn.execute("PRAGMA user_version").fetchone()
            version = cur[0] if cur else 0
            for stmt in _schema.BASE_DDL:
                self.conn.execute(stmt)
            if self.vec_available:
                # dim provider-driven (V2-031): la tabla vec se crea con la dim del embedding ACTIVO (embeddinggemma
                # 768 / bge-m3·e5-large 1024…). IF NOT EXISTS conserva la existente → un cambio de modelo exige
                # `memory/reembed.py` (drop+recreate), avisado por `reembed.check()` al arrancar. Import perezoso.
                from . import embeddings as _emb
                self.conn.execute(_schema.vec_memories_ddl(_emb.dim()))
            if self.fts_available:
                self.conn.execute(_schema.FTS_MEMORIES)
            # v1→v2 (V2-013): la memoria es una PÍLDORA — añade `slot`/`meta` si faltan (ALTER idempotente, no
            # destructivo; SQLite no tiene ADD COLUMN IF NOT EXISTS → miramos las columnas presentes primero).
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(memories)").fetchall()}
            for name, stmt in _schema.MEMORIES_V2_COLUMNS:
                if name not in cols:
                    self.conn.execute(stmt)
            for stmt in _schema.MEMORIES_V2_INDEXES:   # índices que dependen de las columnas v2 (tras el ALTER)
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

    # ── acceso serializado ───────────────────────────────────────────────────────────────────────────────
    @contextmanager
    def cursor(self):
        """Cursor bajo el lock. Hace commit al salir sin excepción, rollback si la hay."""
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

    def execute(self, sql: str, params: tuple | list = ()):  # escritura simple con commit
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


# ── singleton de módulo ─────────────────────────────────────────────────────────────────────────────────
_DB: Database | None = None
_DB_LOCK = threading.Lock()


def get_db() -> Database:
    global _DB
    with _DB_LOCK:
        if _DB is None:
            _DB = Database()
        return _DB


def reset_db():
    """Cierra el singleton (tests / cambio de ZAELAR_DB). La próxima `get_db()` reabre."""
    global _DB
    with _DB_LOCK:
        if _DB is not None:
            _DB.close()
            _DB = None
