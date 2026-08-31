"""Tests for memory/seed_from_hermes.py — idempotent, read-only seeding (V2-003 · T56)."""
import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import seed_from_hermes as seeder
from memory import state as memstate


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


def _fake_hermes(tmp_path):
    d = tmp_path / "hermes_memories"
    d.mkdir()
    (d / "USER.md").write_text(
        "Nombre: Ricard. IDIOMA: castellano por defecto. Dos hijos.\n"
        "§\n"
        "Prefiere respuestas concretas y técnicas, sin divagar.",
        encoding="utf-8",
    )
    (d / "MEMORY.md").write_text(
        "zaelar: asistente cálido, 2 frases por turno.\n"
        "§\n"
        "NUNCA cerrar cluster sin orden del operador.",
        encoding="utf-8",
    )
    return d


def test_seed_populates_state_and_memories(fresh_db, tmp_path):
    d = _fake_hermes(tmp_path)
    rep = seeder.seed(str(d))
    assert rep["source_present"] and rep["seeded"] == 4 and rep["state_updated"]
    st = memstate.read()
    assert st["operator_name"] == "Ricard"
    assert st["language"] == "es"


def test_seed_is_idempotent(fresh_db, tmp_path):
    d = _fake_hermes(tmp_path)
    r1 = seeder.seed(str(d))
    r2 = seeder.seed(str(d))
    assert r1["seeded"] == 4
    assert r2["seeded"] == 0 and r2["skipped"] == 4
    # The state is not rewritten either (there is nothing new to add).
    assert r2["state_updated"] is False


def test_seeded_memories_are_pinned_and_searchable(fresh_db, tmp_path):
    from memory import retriever as memret
    d = _fake_hermes(tmp_path)
    seeder.seed(str(d))
    res = memret.search("cerrar cluster", limit=5, expand=False)
    assert res, "un recuerdo sembrado debe ser buscable"
    row = memdb.get_db().query_one("SELECT pinned FROM memories WHERE text LIKE '%cerrar cluster%'")
    assert row is not None and row["pinned"] == 1


def test_no_hermes_no_error(fresh_db, tmp_path):
    rep = seeder.seed(str(tmp_path / "does_not_exist"))
    assert rep == {"seeded": 0, "skipped": 0, "state_updated": False, "source_present": False}
