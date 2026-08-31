"""Tests for memory/episodic.py (V2-002 · T51) — searchable summary + lazy loading."""
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


def test_register_creates_searchable_summary(fresh_db, tmp_path):
    f = tmp_path / "informe.txt"
    f.write_text("contenido largo del informe sobre Wallapop y precios", encoding="utf-8")
    ref = memep.register(str(f), "resumen: informe de precios de Wallapop", mime="text/plain")
    assert ref["episode_id"] and ref["memory_id"]
    # the summary participates in the search
    res = memret.search("Wallapop", limit=5, expand=False)
    assert any(r["id"] == ref["memory_id"] for r in res)


def test_get_and_by_memory(fresh_db, tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("hola", encoding="utf-8")
    ref = memep.register(str(f), "resumen doc", mime="text/plain")
    ep = memep.get(ref["episode_id"])
    assert ep["path"] == str(f) and ep["mime"] == "text/plain" and ep["bytes"] == 4
    assert memep.by_memory(ref["memory_id"])["id"] == ref["episode_id"]


def test_lazy_load_text_and_bytes(fresh_db, tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("línea uno\nlínea dos", encoding="utf-8")
    ref = memep.register(str(f), "resumen doc")
    assert memep.load_text(ref["episode_id"]).startswith("línea uno")
    assert memep.load_bytes(ref["episode_id"]) == "línea uno\nlínea dos".encode()


def test_lazy_load_missing_file_returns_none(fresh_db, tmp_path):
    ref = memep.register(str(tmp_path / "no_existe.bin"), "resumen fantasma", size=0)
    assert memep.load_bytes(ref["episode_id"]) is None
    assert memep.load_text(ref["episode_id"]) is None
