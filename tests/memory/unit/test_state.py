"""Tests de memory/state.py (V2-002 · T48) — tabla fija, lectura directa sin búsqueda."""
import pytest

from memory import db as memdb
from memory import state as memstate


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    # NO configured language, PINNED: since 2026-08-20 `state.read()` resolves an unset `language` from the active
    # configuration, so a machine whose ⚙ says Spanish would otherwise flip these assertions. A test whose answer
    # depends on the developer's settings is the failure mode this suite already paid for twice today.
    monkeypatch.delenv("ZAELAR_LANGUAGE", raising=False)
    monkeypatch.setattr("voice.engine.core.langs._default_code", lambda: "en")
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


# ── the canonical language FOLLOWS the operator (hole measured 2026-08-20, use_cases sandboxes) ────────────────
def test_a_configured_language_drives_the_memory_canonical_language(tmp_path, monkeypatch):
    """`language` used to be the frozen literal "en" and NOTHING in the tree ever writes the field — the i18n lock
    persists `settings.stt_language`, not the state. So a sandbox started with `ZAELAR_LANGUAGE=es`, logging «text
    channel locked operator language -> 'es'» and talking Spanish for 27 turns, distilled every pill into ENGLISH.

    It cost a real finding too: the tester grepped «vértigo» for a preference that WAS in the turn's prompt as
    "fear of heights", and reported memory as broken when memory had done its job."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "z.db"))
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    memdb.reset_db(); memdb.get_db()
    try:
        assert memstate.read()["language"] == "es"
    finally:
        memdb.reset_db()


def test_an_explicit_stored_language_still_wins_over_the_configuration(tmp_path, monkeypatch):
    """The resolution is only for a state that has NOT been told a language. An explicit choice is a choice."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "z.db"))
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    memdb.reset_db(); memdb.get_db()
    try:
        memstate.patch({"language": "fr"})
        assert memstate.read()["language"] == "fr"
    finally:
        memdb.reset_db()


def test_no_configuration_at_all_still_starts_in_english(tmp_path, monkeypatch):
    """The 2026-07-10 decision stands: what it was against is a HARDCODED language, not English as the start."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "z.db"))
    monkeypatch.delenv("ZAELAR_LANGUAGE", raising=False)
    monkeypatch.setattr("voice.engine.core.langs._default_code", lambda: "en")
    memdb.reset_db(); memdb.get_db()
    try:
        assert memstate.read()["language"] == "en"
    finally:
        memdb.reset_db()
