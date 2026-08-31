"""Tests for memory/writer.py + memory/queue.py (V2-002 · T45)."""
import asyncio

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import writer as memwriter
from memory.queue import MemoryQueue


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    # deterministic backend → fast tests with no network (they do not depend on Ollama).
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
    # vector present
    assert db.query_one("SELECT COUNT(*) c FROM vec_memories WHERE memory_id=?", (mid,))["c"] == 1
    # FTS finds it by keyword
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
    memwriter.link(a, b, "about", 2.0)  # same (from,to,type) → replaces, does not duplicate
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
    # submit without start() → applies inline; the write is not lost.
    q = MemoryQueue()
    q.submit("write", "escritura en linea", kind="event")
    assert memdb.get_db().query_one("SELECT COUNT(*) c FROM memories")["c"] == 1


def test_semantic_dedup_skipped_on_uncalibrated_backend(monkeypatch, fresh_db):
    # 0.45 is calibrated for 'ollama' (embeddinggemma) only (audit 2026-07-26: applying it to 'fastembed' merged
    # unrelated facts — "Te quiero, ánimo con el libro." collapsed into an unrelated boiler-appointment note).
    # hash/fastembed must fall back to exact/slot dedup, never semantic. Patched directly rather than via env var:
    # config/v2.json's stored `embed_provider` outranks ZAELAR_EMBED_BACKEND (store > env, by design), so this repo's
    # actual config state can make the env-var-only fixture above resolve to whatever is stored, not 'hash'.
    monkeypatch.setattr(memwriter._emb, "active_backend", lambda: "fastembed")
    assert memwriter._semantic_dedup_on() is False
    monkeypatch.setattr(memwriter._emb, "active_backend", lambda: "hash")
    assert memwriter._semantic_dedup_on() is False


def test_semantic_dedup_active_on_calibrated_backend(monkeypatch, fresh_db):
    monkeypatch.setattr(memwriter._emb, "active_backend", lambda: "ollama")
    assert memwriter._semantic_dedup_on() is True


def test_unrelated_facts_not_merged_on_uncalibrated_backend(monkeypatch, fresh_db):
    # Same scenario that caused real data loss: force a semantic "hit" (as a miscalibrated threshold would) and
    # verify insert_memory on an uncalibrated backend never even calls the dedup search, so two clearly unrelated
    # durable facts always get their own rows instead of one silently swallowing the other.
    monkeypatch.setattr(memwriter._emb, "active_backend", lambda: "fastembed")
    monkeypatch.setattr(memwriter, "_find_semantic_dup", lambda db, vec: (_ for _ in ()).throw(
        AssertionError("dedup search must not run on an uncalibrated backend")))
    a = memwriter.insert_memory("Te quiero, ánimo con el libro.", level="mid", kind="msg")
    b = memwriter.insert_memory("El técnico de la caldera viene el jueves por la mañana.", level="mid", kind="msg")
    assert a != b
    db = memdb.get_db()
    # both facts must survive as their OWN valid row, verbatim — neither text lost/overwritten by the other
    # (concept-node bookkeeping rows, e.g. "ocio", may also exist alongside these — that's unrelated backstop)
    assert db.query_one("SELECT text FROM memories WHERE id=? AND valid=1", (a,))["text"] == "Te quiero, ánimo con el libro."
    assert db.query_one("SELECT text FROM memories WHERE id=? AND valid=1", (b,))["text"] == \
        "El técnico de la caldera viene el jueves por la mañana."


def test_queue_bad_op_does_not_kill_consumer(fresh_db):
    async def run():
        q = MemoryQueue()
        await q.start()
        badfut = asyncio.get_running_loop().create_future()
        q.submit("no_such_op", 1, future=badfut)
        with pytest.raises(ValueError):
            await asyncio.wait_for(badfut, timeout=5)
        # the consumer remains alive → a subsequent valid write works
        okfut = asyncio.get_running_loop().create_future()
        q.submit("write", "tras el fallo", future=okfut)
        mid = await asyncio.wait_for(okfut, timeout=5)
        await q.stop()
        return mid

    mid = asyncio.run(run())
    assert mid is not None
