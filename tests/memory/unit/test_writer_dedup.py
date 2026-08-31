#
# test_writer_dedup.py — synchronous EXACT deduplication on write (V2-103, 2026-08-16): previously it only
# existed hourly in `consolidator.dedup()`, and that window allowed literal duplicates of the same fact written
# seconds apart (live audit: "Su suegro se llama Pedro." inserted twice, 3s apart).
# No network (hash embeddings). Run: .venv/bin/pytest tests/memory/unit/test_writer_dedup.py
#
import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import writer


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


def test_exact_duplicate_reinforces_not_duplicates(fresh_db):
    a = writer.insert_memory("Su suegro se llama Pedro.", level="long", kind="fact")
    b = writer.insert_memory("Su suegro se llama Pedro.", level="long", kind="fact")
    assert a == b
    db = memdb.get_db()
    rows = db.query("SELECT id, valid FROM memories WHERE text='Su suegro se llama Pedro.'")
    assert len(rows) == 1 and rows[0]["valid"] == 1


def test_exact_duplicate_is_case_insensitive(fresh_db):
    a = writer.insert_memory("Han cancelado el viaje a Ibiza.", level="long", kind="event")
    b = writer.insert_memory("han cancelado el viaje a ibiza.", level="long", kind="event")
    assert a == b


def test_different_text_not_merged(fresh_db):
    a = writer.insert_memory("Le gustan los karts.", level="long", kind="pref")
    b = writer.insert_memory("Le gustan los barcos.", level="long", kind="pref")
    assert a != b


def test_conv_kind_exempt_from_exact_dedup(fresh_db):
    # the conversational buffer must be able to repeat literal text ("sí", "vale") without collapsing it
    a = writer.insert_memory("sí", level="short", kind="conv")
    b = writer.insert_memory("sí", level="short", kind="conv")
    assert a != b


def test_slotted_write_untouched_by_exact_dedup(fresh_db):
    # slot supersession remains the path for singular facts — it must not go through this deduplication
    a = writer.insert_memory("Valencia", level="long", kind="profile", slot="operator.location")
    b = writer.insert_memory("Barcelona", level="long", kind="profile", slot="operator.location")
    assert a != b
    db = memdb.get_db()
    ra = db.query_one("SELECT valid, superseded_by FROM memories WHERE id=?", (a,))
    assert ra["valid"] == 0 and ra["superseded_by"] == b


def test_reinforce_bumps_weight_and_access(fresh_db):
    a = writer.insert_memory("dato repetido", level="long", kind="fact", weight=0.5)
    writer.insert_memory("dato repetido", level="long", kind="fact")
    db = memdb.get_db()
    row = db.query_one("SELECT weight, access_count FROM memories WHERE id=?", (a,))
    assert row["weight"] > 0.5 and row["access_count"] >= 1
