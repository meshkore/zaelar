#
# test_bitemporal.py — valid_at/invalidated_at (V2-111 §9.2, 2026-08-17). `updated` no sirve como "cuándo se
# invalidó": lo toca también el refuerzo y la promoción de nivel del consolidador. Estas dos columnas nuevas
# + `memory/api.py::as_of()` reconstruyen "qué estaba vigente en la fecha X" sin adivinar nada del histórico
# ya conservado. Sin red (embeddings hash). Ejecutar: .venv/bin/pytest tests/memory/unit/test_bitemporal.py
#
import pytest

from memory import api as memapi
from memory import clock as memclock
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


def test_insert_sets_valid_at_to_created(fresh_db):
    with memclock.travel(1_700_000_000):
        mid = writer.insert_memory("Vive en Bilbao.", level="long", kind="fact", slot="operator.location")
    db = memdb.get_db()
    row = db.query_one("SELECT created, valid_at, invalidated_at FROM memories WHERE id=?", (mid,))
    assert row["valid_at"] == row["created"] == 1_700_000_000
    assert row["invalidated_at"] is None


def test_supersede_sets_invalidated_at_only_on_the_old_row(fresh_db):
    with memclock.travel(1_700_000_000):
        old = writer.insert_memory("Vive en Bilbao.", level="long", kind="fact", slot="operator.location")
    with memclock.travel(1_700_100_000):
        new = writer.insert_memory("Vive en Barcelona.", level="long", kind="fact", slot="operator.location")
    db = memdb.get_db()
    old_row = db.query_one("SELECT valid, invalidated_at, superseded_by FROM memories WHERE id=?", (old,))
    new_row = db.query_one("SELECT valid, invalidated_at, valid_at FROM memories WHERE id=?", (new,))
    assert old_row["valid"] == 0
    assert old_row["invalidated_at"] == 1_700_100_000
    assert old_row["superseded_by"] == new
    assert new_row["valid"] == 1
    assert new_row["invalidated_at"] is None
    assert new_row["valid_at"] == 1_700_100_000


def test_reinforcing_same_value_never_sets_invalidated_at(fresh_db):
    with memclock.travel(1_700_000_000):
        mid = writer.insert_memory("Vive en Bilbao.", level="long", kind="fact", slot="operator.location")
    with memclock.travel(1_700_050_000):
        # mismo texto normalizado → reinforce, NO supersede (mismo dato repetido).
        again = writer.insert_memory("Vive en Bilbao.", level="long", kind="fact", slot="operator.location")
    assert again == mid
    db = memdb.get_db()
    row = db.query_one("SELECT valid, invalidated_at FROM memories WHERE id=?", (mid,))
    assert row["valid"] == 1
    assert row["invalidated_at"] is None      # el refuerzo NUNCA es una invalidación


def test_forget_sets_invalidated_at_and_unforget_clears_it(fresh_db):
    with memclock.travel(1_700_000_000):
        mid = writer.insert_memory("Le gustan los karts.", level="long", kind="pref")
    with memclock.travel(1_700_200_000):
        removed = memapi.forget("karts")
    assert removed == 1
    db = memdb.get_db()
    row = db.query_one("SELECT valid, invalidated_at FROM memories WHERE id=?", (mid,))
    assert row["valid"] == 0
    assert row["invalidated_at"] == 1_700_200_000

    with memclock.travel(1_700_300_000):
        restored = memapi.unforget("karts")
    assert restored == 1
    row = db.query_one("SELECT valid, invalidated_at FROM memories WHERE id=?", (mid,))
    assert row["valid"] == 1
    assert row["invalidated_at"] is None      # restaurado: ya no está "cerrado" en una fecha pasada


def test_as_of_reconstructs_past_value_across_a_supersede_chain(fresh_db):
    with memclock.travel(1_700_000_000):
        writer.insert_memory("Vive en Bilbao.", level="long", kind="fact", slot="operator.location")
    with memclock.travel(1_700_100_000):
        writer.insert_memory("Vive en Barcelona.", level="long", kind="fact", slot="operator.location")
    with memclock.travel(1_700_200_000):
        writer.insert_memory("Vive en Valencia.", level="long", kind="fact", slot="operator.location")

    # antes de la primera escritura: no había nada vigente todavía.
    assert memapi.as_of("operator.location", 1_699_999_999) is None
    # justo tras la primera, antes de la segunda: Bilbao.
    row = memapi.as_of("operator.location", 1_700_050_000)
    assert row is not None and "Bilbao" in row["text"]
    # entre la segunda y la tercera: Barcelona.
    row = memapi.as_of("operator.location", 1_700_150_000)
    assert row is not None and "Barcelona" in row["text"]
    # hoy (tras la tercera): Valencia — coincide con lo vigente ahora mismo.
    row = memapi.as_of("operator.location", 1_700_300_000)
    assert row is not None and "Valencia" in row["text"]


def test_as_of_unknown_slot_returns_none(fresh_db):
    assert memapi.as_of("no.existe.este.slot.jamas", 1_700_000_000) is None


def test_as_of_none_slot_returns_none(fresh_db):
    assert memapi.as_of(None, 1_700_000_000) is None
