#
# test_pill_slot.py — memory as a PILL (V2-013): `slot`/`meta` columns, EXACT supersede/dedup by slot,
# and idempotent v1→v2 migration. No network (hash embeddings). Run: .venv/bin/pytest memory/test_pill_slot.py
#
import json

import pytest

from memory import api as memapi
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


def test_schema_v2_has_slot_and_meta(fresh_db):
    d = memdb.get_db()
    assert d.schema_version() >= 2         # v2 = pill (slot/meta); v3 = vault (V2-060) — does not reopen v2
    cols = {r[1] for r in d.conn.execute("PRAGMA table_info(memories)").fetchall()}
    assert "slot" in cols and "meta" in cols


def test_meta_is_stored_as_json(fresh_db):
    mid = writer.insert_memory("dato con meta", level="long", kind="fact",
                               meta={"source": "voice", "said_at": 123})
    row = memdb.get_db().query_one("SELECT meta FROM memories WHERE id=?", (mid,))
    assert json.loads(row["meta"])["source"] == "voice"


def test_slot_supersede_on_value_change(fresh_db):
    a = writer.insert_memory("El operador vive en Madrid.", level="long", kind="profile",
                             slot="operator.location")
    b = writer.insert_memory("El operador vive en Barcelona.", level="long", kind="profile",
                             slot="operator.location")
    assert a != b
    d = memdb.get_db()
    old = d.query_one("SELECT valid, superseded_by FROM memories WHERE id=?", (a,))
    assert old["valid"] == 0 and old["superseded_by"] == b       # the old one remains superseded
    valid = d.query("SELECT COUNT(*) c FROM memories WHERE slot=? AND valid=1", ("operator.location",))
    assert valid[0]["c"] == 1                                     # only ONE current value per slot


def test_slot_dedup_reinforces_on_identical_text(fresh_db):
    a = writer.insert_memory("El operador se llama Ramón.", level="long", kind="profile",
                             slot="operator.name")
    b = writer.insert_memory("  el operador se llama ramón.  ", level="long", kind="profile",
                             slot="operator.name")            # same data (normalized) → reinforces, does not duplicate
    assert a == b
    d = memdb.get_db()
    n = d.query("SELECT COUNT(*) c FROM memories WHERE slot=?", ("operator.name",))[0]["c"]
    assert n == 1                                             # It was NOT duplicated
    w = d.query_one("SELECT weight FROM memories WHERE id=?", (a,))["weight"]
    assert w > 0.5                                            # it was reinforced (weight increased)


def test_no_slot_never_supersedes(fresh_db):
    a = writer.insert_memory("Comió pizza el lunes.", level="short", kind="event")
    b = writer.insert_memory("Comió pasta el martes.", level="short", kind="event")
    assert a != b
    valid = memdb.get_db().query("SELECT COUNT(*) c FROM memories WHERE valid=1")[0]["c"]
    assert valid == 2                                         # without a slot, both coexist


def test_map_exposes_slot_and_meta(fresh_db):
    writer.insert_memory("El operador se llama Ramón.", level="long", kind="profile",
                         slot="operator.name", meta={"source": "voice"})
    m = memapi.map()
    longterm = m["layers"]["long"]
    assert any(x.get("slot") == "operator.name" for x in longterm)
    assert any(x.get("meta") for x in longterm)
