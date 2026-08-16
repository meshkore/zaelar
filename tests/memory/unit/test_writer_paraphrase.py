"""Tests de memory/writer.py::index_paraphrases (V2-031 T2) — índice de vectores de reformulación."""
import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import writer as memwriter


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


def test_index_paraphrases_writes_rows(fresh_db):
    mid = memwriter.insert_memory("toca la guitarra los fines de semana", level="mid", kind="fact")
    done = memwriter.index_paraphrases(mid, ["es músico aficionado", "toca un instrumento de cuerda"])
    assert done == 2
    db = memdb.get_db()
    rows = db.query("SELECT id, memory_id, text FROM paraphrase_index WHERE memory_id=?", (mid,))
    assert len(rows) == 2
    assert {r["text"] for r in rows} == {"es músico aficionado", "toca un instrumento de cuerda"}
    for r in rows:
        vec_row = db.query_one("SELECT id FROM vec_paraphrases WHERE id=?", (r["id"],))
        assert vec_row is not None, "cada fila de paraphrase_index debe tener su vector en vec_paraphrases"


def test_index_paraphrases_caps_at_two_and_skips_empty(fresh_db):
    mid = memwriter.insert_memory("le gusta el senderismo", level="mid", kind="fact")
    done = memwriter.index_paraphrases(mid, ["camina por montaña", "  ", "disfruta de rutas al aire libre"])
    assert done == 2  # el string vacío no cuenta, pero no rompe el resto


def test_index_paraphrases_noop_on_empty_input(fresh_db):
    mid = memwriter.insert_memory("dato cualquiera", level="mid", kind="fact")
    assert memwriter.index_paraphrases(mid, []) == 0
    assert memwriter.index_paraphrases(0, ["texto"]) == 0
    assert memwriter.index_paraphrases(mid, None) == 0


def test_index_paraphrases_fail_open_on_degraded_backend(fresh_db, monkeypatch):
    mid = memwriter.insert_memory("dato cualquiera", level="mid", kind="fact")
    monkeypatch.setattr(mememb, "last_degraded", True)
    assert memwriter.index_paraphrases(mid, ["reformulación"]) == 0
    db = memdb.get_db()
    assert db.query_one("SELECT COUNT(*) c FROM paraphrase_index")["c"] == 0
