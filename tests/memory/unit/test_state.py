"""Tests de memory/state.py (V2-002 · T48) — tabla fija, lectura directa sin búsqueda."""
import pytest

from memory import db as memdb
from memory import state as memstate


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def test_a_new_account_starts_in_english_and_empty(fresh_db):
    """This test used to be called `test_default_is_spanish` and asserted exactly that — it encoded the bug
    rather than the contract. The product opens in ENGLISH and switches to the operator's real language on
    their first sentence (see tests/voice/unit/test_language_bootstrap.py). This field is the one the memory
    CORAZÓN reads to pick the language it distils every pill in, so a state that starts in Spanish commits a
    brand-new account's memory to a language its owner never chose."""
    s = memstate.read()
    assert s["language"] == "en"
    assert s["assistant_name"] == "Zaelar"
    # And EMPTY: a fresh account owns no identity, no mission and no rules yet.
    assert s["operator_name"] is None
    assert s["mission"] is None
    assert not s.get("rules")


def test_write_and_read_roundtrip(fresh_db):
    memstate.write({"operator_name": "Ricart", "location": "Barcelona"})
    s = memstate.read()
    assert s["operator_name"] == "Ricart"
    assert s["location"] == "Barcelona"
    assert s["language"] == "en"  # el default se conserva al escribir otros campos


def test_patch_is_shallow_merge(fresh_db):
    memstate.write({"operator_name": "Ricart", "topics": ["colmena"]})
    memstate.patch({"treatment": "directo, sin narrar"})
    s = memstate.read()
    assert s["operator_name"] == "Ricart"        # no se perdió
    assert s["treatment"] == "directo, sin narrar"
    assert s["topics"] == ["colmena"]


def test_single_row_only(fresh_db):
    memstate.write({"operator_name": "A"})
    memstate.write({"operator_name": "B"})
    n = memdb.get_db().query_one("SELECT COUNT(*) c FROM state")["c"]
    assert n == 1  # fila única (id=1)
    assert memstate.read()["operator_name"] == "B"


def test_read_does_not_hit_index(fresh_db):
    # sanity: read solo hace un SELECT por PK; no depende de vec/fts.
    memstate.write({"operator_name": "Ricart"})
    assert memstate.read()["operator_name"] == "Ricart"
