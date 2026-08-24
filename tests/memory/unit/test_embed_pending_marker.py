"""`meta.embed_pending` vale el MOTIVO, nunca un 1 — y quien lo consulte tiene que preguntarlo por ausencia.

Nadie probaba la FORMA de este marcador (2026-08-24: cero menciones en `tests/`), y el comentario que lo
describe en `writer.py` decía `meta.embed_pending=1` mientras `_mark_embed_pending` escribe la cadena del
motivo. La mentira costó un diagnóstico ese mismo día: consulté las bases del plató con
`embed_pending = 1`, salió **0 pendientes** sobre una base que tenía una fila dañada, y estuve a punto de
informar de «limpio». Lo cazó ir a mirar con qué predicado consulta el producto (`rem.py`, `IS NOT NULL`).

La clase de fallo es la peor de las baratas: **una consulta que no puede encontrar nada informa igual que una
base sana**. No falla, no avisa, y su respuesta es tranquilizadora justo cuando hay daño.

Así que aquí se clava lo que un consumidor puede dar por hecho:
  · el marcador guarda el MOTIVO y no un booleano — si alguien lo «simplifica» a 1, esto se pone rojo;
  · un `= 1` es estructuralmente ciego, y se comprueba EJECUTÁNDOLO contra una fila marcada de verdad;
  · el motivo es legible, porque «esta píldora no tiene vector» y «no lo tiene porque el índice está sellado
    con otro modelo» llevan a acciones distintas.

No se prueba el comentario (no se puede). Se prueba el contrato que el comentario describía mal.
"""
from __future__ import annotations

import json

import pytest

from memory import db as memdb
from memory import writer as memwriter


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _marca(mid: int) -> object:
    row = memdb.get_db().query_one("SELECT meta FROM memories WHERE id=?", (mid,))
    return json.loads(row["meta"] or "{}").get("embed_pending")


def test_el_marcador_guarda_el_MOTIVO_y_no_un_booleano(fresh_db):
    mid = memwriter.insert_memory("un hecho sin vector", weight=0.5)
    memwriter._mark_embed_pending(memdb.get_db(), mid, "sig_mismatch")

    v = _marca(mid)
    assert v == "sig_mismatch"
    assert not isinstance(v, bool) and v != 1, (
        "si el marcador pasa a ser 1/True, toda consulta `IS NOT NULL` sigue funcionando pero se pierde el "
        "MOTIVO — y «no tiene vector» y «el índice está sellado con otro modelo» piden cosas distintas")


def test_una_consulta_por_IGUAL_A_1_es_CIEGA_y_se_demuestra_corriendola(fresh_db):
    """El error real, reproducido: sobre una base CON daño, `= 1` cuenta cero y `IS NOT NULL` cuenta uno."""
    mid = memwriter.insert_memory("otra sin vector", weight=0.5)
    memwriter._mark_embed_pending(memdb.get_db(), mid, "degraded")

    ciega = memdb.get_db().query_one(
        "SELECT COUNT(*) c FROM memories WHERE valid=1 "
        "AND COALESCE(json_extract(meta,'$.embed_pending'),0)=1")["c"]
    buena = memdb.get_db().query_one(
        "SELECT COUNT(*) c FROM memories WHERE valid=1 "
        "AND json_extract(meta,'$.embed_pending') IS NOT NULL")["c"]

    assert buena == 1, "la fila dañada existe"
    assert ciega == 0, (
        "esta es la trampa entera: la consulta equivocada no falla, contesta CERO — «todo limpio» sobre una "
        "base con daño. Si algún día devolviera 1, este test sobra y el marcador cambió de forma")


def test_los_DOS_motivos_que_escribe_el_writer_son_legibles(fresh_db):
    """Los motivos son los que el propio `insert_memory` produce; si nace un tercero, que se declare aquí."""
    for razon in ("sig_mismatch", "degraded"):
        mid = memwriter.insert_memory(f"pildora {razon}", weight=0.5)
        memwriter._mark_embed_pending(memdb.get_db(), mid, razon)
        assert _marca(mid) == razon


def test_marcar_NUNCA_lanza_aunque_la_fila_no_exista(fresh_db):
    """Corre dentro de una escritura ya hecha: reventar aquí perdería la píldora, que sí se guardó bien."""
    memwriter._mark_embed_pending(memdb.get_db(), 999_999, "sig_mismatch")   # no debe lanzar
