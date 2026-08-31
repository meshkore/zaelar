#
# test_widget_slot_migration.py — v5→v6 migration (V2-242, 2026-08-21): the pills written by a widget tick are
# renamed so that their slot contains the AUTHOR (`<widget-id>:<key>`).
#
# Why it exists: the two readers that separate “operator facts” from “background job output” do so by the SHAPE
# of the key (passive block since the 2026-07-14 audit; worker dossier since 2026-08-21). `TickCtx.remember`
# already enforces this when writing, but superseding uses the EXACT slot: without this migration, a
# `weather:soria` written for months is never replaced by the new `meteo-soria:weather:soria`, and the
# installation is left with TWO live lineages, the old one frozen and competing during recall.
#
# Run: .venv/bin/pytest tests/memory/unit/test_widget_slot_migration.py
#
import json
import sqlite3

import pytest

from memory import db as memdb
from memory import embeddings as mememb


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


def _v5_db_with(path, rows):
    """Create a database, mark it as v5, and insert rows using the OLD slot format."""
    memdb.reset_db()
    db = memdb.get_db()                                   # create the complete schema
    for text, slot, widget, updated in rows:
        meta = json.dumps({"widget": widget}) if widget else None
        db.execute("INSERT INTO memories (text, level, kind, slot, meta, valid, importance, weight, "
                   "created, updated) VALUES (?,'mid','note',?,?,1,0.3,0.5,?,?)",
                   (text, slot, meta, updated, updated))
    db.execute("PRAGMA user_version=5")                   # force the state BEFORE the migration
    memdb.reset_db()
    return sqlite3.connect(path)


def _slots(path):
    con = sqlite3.connect(path)
    out = [(r[0], r[1], r[2]) for r in con.execute("SELECT slot, valid, text FROM memories ORDER BY id")]
    con.close()
    return out


def test_old_widget_pill_gets_its_author_into_the_key(tmp_path, monkeypatch):
    path = str(tmp_path / "zaelar.db")
    monkeypatch.setenv("ZAELAR_DB", path)
    _v5_db_with(path, [("Weather in Soria now: 14.5C.", "weather:soria", "meteo-soria", 1000)])

    memdb.get_db()                                        # opening the database triggers the migration
    assert memdb.get_db().schema_version() >= 6
    assert _slots(path) == [("meteo-soria:weather:soria", 1, "Weather in Soria now: 14.5C.")]
    memdb.reset_db()


def test_the_two_lineages_collapse_and_the_newest_wins(tmp_path, monkeypatch):
    """The case motivating the migration: the old and new keys coexist, and without collapsing them the old one
    remains frozen forever, competing during recall."""
    path = str(tmp_path / "zaelar.db")
    monkeypatch.setenv("ZAELAR_DB", path)
    _v5_db_with(path, [
        ("Weather in Soria now: 14.5C.", "weather:soria", "meteo-soria", 1000),              # old
        ("Weather in Soria now: 21.0C.", "meteo-soria:weather:soria", "meteo-soria", 2000),  # new
    ])

    memdb.get_db()
    got = _slots(path)
    assert all(s == "meteo-soria:weather:soria" for s, _v, _t in got)     # a single key
    vivas = [t for _s, v, t in got if v == 1]
    assert vivas == ["Weather in Soria now: 21.0C."]                       # the MOST RECENT one wins
    memdb.reset_db()


def test_a_note_with_no_slot_stops_being_indistinguishable_from_an_operator_fact(tmp_path, monkeypatch):
    """A note WITHOUT a slot is not filtered by anyone either (there is no ':' to read) — it becomes `<widget>:note`."""
    path = str(tmp_path / "zaelar.db")
    monkeypatch.setenv("ZAELAR_DB", path)
    _v5_db_with(path, [("Champions: el sorteo es el jueves.", None, "futbol-champions", 1000)])

    memdb.get_db()
    assert _slots(path)[0][0] == "futbol-champions:note"
    memdb.reset_db()


def test_the_operators_own_pills_are_never_moved(tmp_path, monkeypatch):
    """Without `meta.widget` there is no background author: an operator slot is NOT touched, even if it has no ':'."""
    path = str(tmp_path / "zaelar.db")
    monkeypatch.setenv("ZAELAR_DB", path)
    _v5_db_with(path, [
        ("Vive en el centro de Madrid.", "operator.location", None, 1000),
        ("Una nota suelta sin slot.", None, None, 1000),
    ])

    memdb.get_db()
    assert [s for s, _v, _t in _slots(path)] == ["operator.location", None]
    memdb.reset_db()


def test_migration_is_idempotent(tmp_path, monkeypatch):
    """Opening the database twice does not move anything again — the second pass is skipped (version >= 6)."""
    path = str(tmp_path / "zaelar.db")
    monkeypatch.setenv("ZAELAR_DB", path)
    _v5_db_with(path, [("Weather in Soria now: 14.5C.", "weather:soria", "meteo-soria", 1000)])

    memdb.get_db(); memdb.reset_db()
    first = _slots(path)
    memdb.get_db(); memdb.reset_db()
    assert _slots(path) == first
