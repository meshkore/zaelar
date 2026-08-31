"""Tests for memory/episodic.py — bytes in the data directory + searchable summary + migration (V2-003 · T53)."""
import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import episodic as memep
from memory import retriever as memret


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
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


def test_write_episode_stores_bytes_in_memory_datadir(fresh_db):
    ref = memep.write_episode(b"hola mundo", filename="nota.txt", mime="text/plain")
    assert ref["episode_id"] and ref["memory_id"]
    # the binary lives under the memory data directory, not in files/uploads/
    assert "episodic" in ref["path"]
    assert memep.load_bytes(ref["episode_id"]) == b"hola mundo"


def test_write_episode_summary_is_searchable(fresh_db):
    ref = memep.write_episode(
        "informe de precios de Wallapop en Barcelona".encode(),
        filename="informe.txt", mime="text/plain",
    )
    res = memret.search("Wallapop", limit=5, expand=False)
    assert any(r["id"] == ref["memory_id"] for r in res)


def test_write_episode_binary_summary_by_name(fresh_db):
    ref = memep.write_episode(b"\x89PNG\r\n\x1a\n\x00\x01", filename="captura.png", mime="image/png")
    # binary → the summary relies on the name; searchable by that name
    res = memret.search("captura", limit=5, expand=False)
    assert any(r["id"] == ref["memory_id"] for r in res)
    # the binary loads lazily and matches byte for byte
    assert memep.load_bytes(ref["episode_id"]) == b"\x89PNG\r\n\x1a\n\x00\x01"


def test_write_episode_no_collision_overwrite(fresh_db):
    a = memep.write_episode(b"uno", filename="dup.txt")
    b = memep.write_episode(b"dos", filename="dup.txt")
    assert a["path"] != b["path"]
    assert memep.load_bytes(a["episode_id"]) == b"uno"
    assert memep.load_bytes(b["episode_id"]) == b"dos"


def test_migrate_inbox_idempotent_and_non_destructive(fresh_db, tmp_path):
    inbox = tmp_path / "old_uploads"
    inbox.mkdir()
    (inbox / "viejo.txt").write_text("contenido de Wallapop antiguo", encoding="utf-8")
    rep1 = memep.migrate_inbox(str(inbox))
    assert rep1["migrated"] == ["viejo.txt"]
    # NON-destructive: the source still exists
    assert (inbox / "viejo.txt").is_file()
    # idempotent: a second pass does not re-import
    rep2 = memep.migrate_inbox(str(inbox))
    assert rep2["migrated"] == [] and rep2["skipped"] == 1
    # and the migrated episode is searchable
    assert any("viejo" in e["name"] for e in memep.list_episodes())


def test_list_episodes(fresh_db):
    memep.write_episode(b"a", filename="a.txt")
    memep.write_episode(b"b", filename="b.txt")
    names = {e["name"] for e in memep.list_episodes()}
    assert {"a.txt", "b.txt"} <= names
