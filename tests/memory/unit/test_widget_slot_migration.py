#
# test_widget_slot_migration.py — migración v5→v6 (V2-242, 2026-08-21): las píldoras que escribió un tick de
# widget se renombran para que su slot lleve el AUTOR (`<widget-id>:<clave>`).
#
# Por qué existe: los dos lectores que separan «hechos del operador» de «volcado de un trabajo de fondo» lo
# hacen por la FORMA de la clave (bloque pasivo desde la auditoría 2026-07-14; dossier del worker desde
# 2026-08-21). `TickCtx.remember` ya lo impone al escribir, pero el supersede es por slot EXACTO: sin esta
# migración un `weather:soria` escrito durante meses no lo sustituye nunca el nuevo `meteo-soria:weather:soria`
# y la instalación se queda con DOS linajes vivos, el viejo congelado y compitiendo en el recall.
#
# Ejecutar: .venv/bin/pytest tests/memory/unit/test_widget_slot_migration.py
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
    """Crea una BD, la deja marcada como v5 y le mete filas con la forma VIEJA de slot."""
    memdb.reset_db()
    db = memdb.get_db()                                   # crea el esquema completo
    for text, slot, widget, updated in rows:
        meta = json.dumps({"widget": widget}) if widget else None
        db.execute("INSERT INTO memories (text, level, kind, slot, meta, valid, importance, weight, "
                   "created, updated) VALUES (?,'mid','note',?,?,1,0.3,0.5,?,?)",
                   (text, slot, meta, updated, updated))
    db.execute("PRAGMA user_version=5")                   # fuerza el estado ANTERIOR a la migración
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

    memdb.get_db()                                        # abrir la BD dispara la migración
    assert memdb.get_db().schema_version() >= 6
    assert _slots(path) == [("meteo-soria:weather:soria", 1, "Weather in Soria now: 14.5C.")]
    memdb.reset_db()


def test_the_two_lineages_collapse_and_the_newest_wins(tmp_path, monkeypatch):
    """El caso que motiva la migración: la clave vieja y la nueva conviven, y sin colapsar la vieja se queda
    congelada para siempre compitiendo en el recall."""
    path = str(tmp_path / "zaelar.db")
    monkeypatch.setenv("ZAELAR_DB", path)
    _v5_db_with(path, [
        ("Weather in Soria now: 14.5C.", "weather:soria", "meteo-soria", 1000),              # vieja
        ("Weather in Soria now: 21.0C.", "meteo-soria:weather:soria", "meteo-soria", 2000),  # nueva
    ])

    memdb.get_db()
    got = _slots(path)
    assert all(s == "meteo-soria:weather:soria" for s, _v, _t in got)     # una sola clave
    vivas = [t for _s, v, t in got if v == 1]
    assert vivas == ["Weather in Soria now: 21.0C."]                       # gana la MÁS RECIENTE
    memdb.reset_db()


def test_a_note_with_no_slot_stops_being_indistinguishable_from_an_operator_fact(tmp_path, monkeypatch):
    """Una nota SIN slot tampoco la filtra nadie (no hay ':' que leer) — pasa a `<widget>:note`."""
    path = str(tmp_path / "zaelar.db")
    monkeypatch.setenv("ZAELAR_DB", path)
    _v5_db_with(path, [("Champions: el sorteo es el jueves.", None, "futbol-champions", 1000)])

    memdb.get_db()
    assert _slots(path)[0][0] == "futbol-champions:note"
    memdb.reset_db()


def test_the_operators_own_pills_are_never_moved(tmp_path, monkeypatch):
    """Sin `meta.widget` no hay autor de fondo: un slot del operador NO se toca, ni siquiera si no lleva ':'."""
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
    """Abrir la BD dos veces no vuelve a mover nada — la segunda pasada ya no entra (version >= 6)."""
    path = str(tmp_path / "zaelar.db")
    monkeypatch.setenv("ZAELAR_DB", path)
    _v5_db_with(path, [("Weather in Soria now: 14.5C.", "weather:soria", "meteo-soria", 1000)])

    memdb.get_db(); memdb.reset_db()
    first = _slots(path)
    memdb.get_db(); memdb.reset_db()
    assert _slots(path) == first
