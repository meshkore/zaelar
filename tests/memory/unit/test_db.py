"""Tests de memory/db.py + memory/schema.py (V2-002 · T44)."""
import sqlite3

import pytest

from memory import db as memdb
from memory import schema as memschema


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    d = memdb.get_db()
    yield d
    memdb.reset_db()


def test_opens_in_wal(fresh_db):
    mode = fresh_db.conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    assert fresh_db.path.exists()


def test_base_tables_created(fresh_db):
    t = fresh_db.tables()
    for name in ("state", "memories", "edges", "episodic", "journal"):
        assert name in t, f"falta la tabla {name}"


def test_schema_version_set(fresh_db):
    assert fresh_db.schema_version() == memschema.SCHEMA_VERSION


def test_fts_table_present(fresh_db):
    # FTS5 viene en la amalgama estándar → debe estar disponible en el sqlite del venv.
    assert fresh_db.fts_available is True
    assert "fts_memories" in fresh_db.tables()


def test_vec_table_present_when_available(fresh_db):
    # sqlite-vec está instalado en el venv (requirements) → vec_available True + tabla creada.
    assert fresh_db.vec_available is True
    assert "vec_memories" in fresh_db.tables()
    # la columna vector tiene la dimensión del schema
    ver = fresh_db.conn.execute("SELECT vec_version()").fetchone()[0]
    assert ver.startswith("v0.1")


def test_memories_roundtrip_insert(fresh_db):
    now = 1000
    rid = fresh_db.execute(
        "INSERT INTO memories (level, kind, text, created, updated) VALUES (?,?,?,?,?)",
        ("short", "fact", "el operador se llama Ricart", now, now),
    )
    row = fresh_db.query_one("SELECT text, weight, valid, pinned FROM memories WHERE id=?", (rid,))
    assert row["text"] == "el operador se llama Ricart"
    assert row["weight"] == pytest.approx(0.5)
    assert row["valid"] == 1
    assert row["pinned"] == 0


def test_migrate_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    d1 = memdb.get_db()
    d1.execute(
        "INSERT INTO memories (level, kind, text, created, updated) VALUES ('short','fact','x',1,1)"
    )
    memdb.reset_db()
    d2 = memdb.get_db()  # reabre el mismo fichero → migración no debe borrar nada
    assert d2.query_one("SELECT COUNT(*) c FROM memories")["c"] == 1
    assert d2.schema_version() == memschema.SCHEMA_VERSION
    memdb.reset_db()


def test_get_db_survives_reentrant_call_from_inside_migrate(tmp_path, monkeypatch):
    """Real deadlock, 2026-08-16: on a FRESH db, Database.__init__ -> _migrate() -> embeddings.dim() ->
    _resolve_backend() -> _ollama_embed() logs perf via voice.observer.perf() -> emit() -> stamp_identity()
    -> nucleo.runstate.stopped() -> kv_get() -> get_db() AGAIN, same thread, before the first get_db() call
    has returned (_DB is still None). A plain threading.Lock self-deadlocks there on every fresh boot —
    reproduced here directly against the lock, without the full observer/runstate chain."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    from memory import embeddings as memembed
    reentered = {"n": 0}
    real_dim = memembed.dim

    def _reentrant_dim():
        reentered["n"] += 1
        if reentered["n"] == 1:
            memdb.get_db()  # same thread, _DB still None, _DB_LOCK still held by the outer get_db()
        return real_dim()

    monkeypatch.setattr(memembed, "dim", _reentrant_dim)
    import threading
    done = threading.Event()

    def _open():
        memdb.get_db()
        done.set()

    t = threading.Thread(target=_open, daemon=True)
    t.start()
    t.join(timeout=5)
    assert done.is_set(), "get_db() deadlocked on reentrant call — _DB_LOCK must be an RLock, not a Lock"
    memdb.reset_db()


def test_vec_search_smoke(fresh_db):
    """La tabla vec0 acepta insertar/consultar un vector de la dimensión correcta."""
    dim = memschema.EMBED_DIM
    import struct

    def blob(vec):
        return struct.pack(f"{len(vec)}f", *vec)

    fresh_db.execute("INSERT INTO memories (level,kind,text,created,updated) VALUES ('short','fact','a',1,1)")
    fresh_db.execute(
        "INSERT INTO vec_memories (memory_id, embedding) VALUES (1, ?)", (blob([0.1] * dim),)
    )
    rows = fresh_db.query(
        "SELECT memory_id, distance FROM vec_memories WHERE embedding MATCH ? ORDER BY distance LIMIT 3",
        (blob([0.1] * dim),),
    )
    assert rows and rows[0]["memory_id"] == 1
