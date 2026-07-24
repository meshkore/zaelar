"""Tests de memory/writer.py + memory/queue.py (V2-002 · T45)."""
import asyncio

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import writer as memwriter
from memory.queue import MemoryQueue


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    # backend determinista → tests rápidos y sin red (no dependen de Ollama).
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def test_insert_syncs_all_three(fresh_db):
    mid = memwriter.insert_memory("el operador vive en Barcelona", level="long", kind="fact")
    db = memdb.get_db()
    assert db.query_one("SELECT text FROM memories WHERE id=?", (mid,))["text"].startswith("el operador")
    # vector presente
    assert db.query_one("SELECT COUNT(*) c FROM vec_memories WHERE memory_id=?", (mid,))["c"] == 1
    # fts encuentra por keyword
    hit = db.query_one("SELECT rowid FROM fts_memories WHERE fts_memories MATCH 'Barcelona'")
    assert hit is not None and hit["rowid"] == mid


def test_importance_defaults_by_kind(fresh_db):
    mid = memwriter.insert_memory("me gusta el café solo", kind="pref")
    imp = memdb.get_db().query_one("SELECT importance FROM memories WHERE id=?", (mid,))["importance"]
    assert imp == pytest.approx(0.7)


def test_reinforce_raises_weight_and_recency(fresh_db):
    mid = memwriter.insert_memory("dato", kind="event", weight=0.5)
    before = memdb.get_db().query_one("SELECT weight, access_count, last_access FROM memories WHERE id=?", (mid,))
    memwriter.reinforce([mid])
    after = memdb.get_db().query_one("SELECT weight, access_count, last_access FROM memories WHERE id=?", (mid,))
    assert after["weight"] > before["weight"]
    assert after["access_count"] == before["access_count"] + 1
    assert after["last_access"] >= before["last_access"]


def test_reinforce_caps_at_one(fresh_db):
    mid = memwriter.insert_memory("dato", weight=0.95)
    for _ in range(5):
        memwriter.reinforce([mid])
    w = memdb.get_db().query_one("SELECT weight FROM memories WHERE id=?", (mid,))["weight"]
    assert w == pytest.approx(1.0)


def test_delete_cleans_vec_and_fts(fresh_db):
    mid = memwriter.insert_memory("borrable Barcelona", kind="event")
    memwriter.delete_memory(mid)
    db = memdb.get_db()
    assert db.query_one("SELECT COUNT(*) c FROM memories WHERE id=?", (mid,))["c"] == 0
    assert db.query_one("SELECT COUNT(*) c FROM vec_memories WHERE memory_id=?", (mid,))["c"] == 0
    assert db.query_one("SELECT COUNT(*) c FROM fts_memories WHERE fts_memories MATCH 'Barcelona'")["c"] == 0


def test_link_is_idempotent(fresh_db):
    a = memwriter.insert_memory("a")
    b = memwriter.insert_memory("b")
    memwriter.link(a, b, "about", 1.0)
    memwriter.link(a, b, "about", 2.0)  # mismo (from,to,type) → reemplaza, no duplica
    rows = memdb.get_db().query("SELECT weight FROM edges WHERE from_id=? AND to_id=? AND type='about'", (a, b))
    assert len(rows) == 1 and rows[0]["weight"] == pytest.approx(2.0)


def test_queue_single_writer_roundtrip(fresh_db):
    async def run():
        q = MemoryQueue()
        await q.start()
        fut = asyncio.get_running_loop().create_future()
        q.submit("write", "recuerdo por la cola", future=fut, kind="fact", level="long")
        mid = await asyncio.wait_for(fut, timeout=5)
        await q.join()
        await q.stop()
        return mid

    mid = asyncio.run(run())
    row = memdb.get_db().query_one("SELECT text, kind FROM memories WHERE id=?", (mid,))
    assert row["text"] == "recuerdo por la cola" and row["kind"] == "fact"


def test_queue_inline_when_not_started(fresh_db):
    # submit sin start() → aplica en línea, no se pierde la escritura.
    q = MemoryQueue()
    q.submit("write", "escritura en linea", kind="event")
    assert memdb.get_db().query_one("SELECT COUNT(*) c FROM memories")["c"] == 1


def test_queue_bad_op_does_not_kill_consumer(fresh_db):
    async def run():
        q = MemoryQueue()
        await q.start()
        badfut = asyncio.get_running_loop().create_future()
        q.submit("no_such_op", 1, future=badfut)
        with pytest.raises(ValueError):
            await asyncio.wait_for(badfut, timeout=5)
        # el consumidor sigue vivo → una escritura buena después funciona
        okfut = asyncio.get_running_loop().create_future()
        q.submit("write", "tras el fallo", future=okfut)
        mid = await asyncio.wait_for(okfut, timeout=5)
        await q.stop()
        return mid

    mid = asyncio.run(run())
    assert mid is not None
