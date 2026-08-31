"""Tests for memory/db.py + memory/schema.py (V2-002 · T44)."""
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
    # FTS5 comes with the standard amalgamation → it should be available in the venv's sqlite.
    assert fresh_db.fts_available is True
    assert "fts_memories" in fresh_db.tables()


def test_vec_table_present_when_available(fresh_db):
    # sqlite-vec is installed in the venv (requirements) → vec_available True + table created.
    assert fresh_db.vec_available is True
    assert "vec_memories" in fresh_db.tables()
    # The vector column has the schema's dimension.
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
    d2 = memdb.get_db()  # reopens the same file → migration must not delete anything
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
    """The vec0 table accepts inserting/querying a vector of the correct dimension."""
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


# ── by_slot_prefix: read a CATALOGUE by key, without paying for semantic recall (V2-260, 2026-08-21) ──────────
# Requested by the harness so that «¿qué electricistas tenemos?» is a prefix SELECT rather than an embedding + RRF
# + reranker. The use case it serves has the success criterion that the `worker` family must NOT appear, so
# semantic recall here would be precisely the expensive process the catalogue exists to avoid.

def test_by_slot_prefix_reads_a_catalogue_by_key(fresh_db):
    from memory import api as memapi
    memapi.write_now("Electricistas Ruiz — 24h — 91 555 00 11", level="mid", kind="note",
                     slot="candidato:electricista:a1", importance=0.5)
    memapi.write_now("ElectroMadrid — urgencias — 91 555 22 33", level="mid", kind="note",
                     slot="candidato:electricista:b2", importance=0.5)
    memapi.write_now("Fontanería Gómez", level="mid", kind="note",
                     slot="candidato:fontanero:c3", importance=0.5)
    memapi.write_now("Vive en el centro de Madrid.", level="long", kind="profile",
                     slot="operator.location", importance=0.9)

    got = memapi.by_slot_prefix("candidato:electricista:")
    assert {m["slot"] for m in got} == {"candidato:electricista:a1", "candidato:electricista:b2"}
    assert memapi.by_slot_prefix("candidato:") and len(memapi.by_slot_prefix("candidato:")) == 3
    assert memapi.by_slot_prefix("") == []


def test_by_slot_prefix_escapes_the_LIKE_wildcards(fresh_db):
    """`_` and `%` are SQL wildcards, and slots naturally contain underscores. Without escaping,
    `candidato:aire_acondicionado:` ALSO returns `candidato:aireXacondicionado:` — verified in sqlite
    before writing the function. A catalogue that drags in entries from another category does not fail: it over-answers."""
    from memory import api as memapi
    memapi.write_now("Clima Sur — instalación", level="mid", kind="note",
                     slot="candidato:aire_acondicionado:a1", importance=0.5)
    memapi.write_now("IMPOSTOR — otra categoría", level="mid", kind="note",
                     slot="candidato:aireXacondicionado:zz", importance=0.5)

    got = memapi.by_slot_prefix("candidato:aire_acondicionado:")
    assert [m["slot"] for m in got] == ["candidato:aire_acondicionado:a1"]


def test_by_slot_prefix_hides_what_the_writer_invalidated(fresh_db):
    """A candidate's expiration is `ttl_days` + consolidator (`created + ttl_days`), not decay. This fixes
    half of the read behavior: invalidated entries do NOT appear, regardless of their weight."""
    from memory import api as memapi
    from memory import db as memdb
    memapi.write_now("Caducado S.L.", level="mid", kind="note", slot="candidato:electricista:old",
                     importance=0.5)
    memdb.get_db().execute("UPDATE memories SET valid=0 WHERE slot='candidato:electricista:old'")
    assert memapi.by_slot_prefix("candidato:electricista:") == []
