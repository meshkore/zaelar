"""El reloj de la entrega es el de la HOJA, no el de la narración del navegador (2026-08-24).

`sheet_timing` es el campo con el que se decide la pregunta más cara de esta suite: si el agente TUVO
resultados y no los dijo (conducta) o si el navegador acabó después de que se agotaran los turnos (latencia).
Mandan a arreglar mitades opuestas del sistema. Tenía dos defectos, los dos medidos:

1. `id == "results"`, comparación EXACTA contra el id de antes de V2-259, cuando la hoja era una. Desde
   entonces cada encargo abre la suya (`results::<id>`) y ese `show` no casaba con nada. Lo único que casaba
   era el de la caja pelada… que lo emite el ECO del canvas (`src="user"`), o sea el fantasma que V2-261
   filtra en el frontend. `sheet_ms` medía cuándo apareció una tarjeta que no abrió nadie.

2. `first_result_ms` salía de un evento `navegador` cuyo TEXTO parseara como items — o sea cuándo el
   navegador CONTÓ una extracción, no cuándo la hoja recibió filas. Sobre la misma hoja de la ronda de las
   18:02: filas a las **18:02:39**, narración a las **18:14:36**. Doce minutos. Todos los «llegó 42 s antes /
   163 s después» de esa tanda se midieron contra ese reloj.

Y estrenar una hoja no es llenarla: la apertura emite su propio `data`, así que sin distinguirlo el reloj de
las filas cae en el mismo instante que el de la apertura y TODA ronda parece haber entregado al principio —
la mentira más cómoda que este campo podría contar. Lo que los separa es `src`, medido siguiendo una hoja
entera:

    18:02:00  data   results--c30db3-1  src=system     ← la apertura (espejo de disco)
    18:02:00  show   results::c30db3-1  src=worker:1   ← la hoja se abre
    18:02:39  data   results::c30db3-1  src=worker     ← aquí empiezan a caer filas
    18:09:26  blank  results--c30db3-1  src=system     ← un vaciado
"""
import json
import sqlite3

import pytest

from tests.use_cases.e2e.agent import verify


def _db(tmp_path, events):
    """Una base con la forma REAL de `events` — columnas incluidas, que ya han mordido una vez hoy."""
    p = tmp_path / "s.db"
    con = sqlite3.connect(str(p))
    con.execute("CREATE TABLE events (ts_ms REAL, topic TEXT, kind TEXT, label TEXT, payload TEXT)")
    for ts, kind, label, ident, src in events:
        con.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                    (ts, "observer", kind, label,
                     json.dumps({"id": ident, "label": label, "src": src})))
    con.commit(); con.close()
    return str(p)


# La ronda de las 18:02 tal cual salió del registro — CORREGIDA el 2026-08-24 (V2-300) con lo que enseñó la
# ronda 23: un `data src=worker` SIN `op` es el repintado de FASE (`sheets.record_phase`, «no hay nada que
# guardar»), no una fila. En la 23 ese repintado adelantó el reloj 104 s y el juez archivó [alta] una «hoja
# llena» que estaba VACÍA — el turno decía la verdad y el instrumento acusó al producto. La entrega real es
# el intake (`src=navegador`) o una data-op del worker por el puente, que viaja CON su `op`.
REAL = [
    (1000.0, "widget", "data",  "results--c30db3-1", "system"),
    (1000.0, "widget", "show",  "results::c30db3-1", "worker:1"),
    (20000.0, "widget", "data", "results::c30db3-1", "worker"),      # repintado de fase — NO es una fila
    (39000.0, "widget", "data", "results::c30db3-1", "navegador"),   # el intake: aquí caen filas de verdad
    (60000.0, "widget", "data", "results::c30db3-1", "worker"),
]


def test_la_hoja_del_ENCARGO_es_la_que_se_mide(tmp_path):
    out = verify.sheet_timing(_db(tmp_path, REAL))
    assert out["sheet_box"] == "c30db3-1", "se mide la hoja del encargo, no la caja pelada"
    assert out["sheet_ms"] == 1000.0


def test_el_ECO_de_la_caja_pelada_no_cuenta(tmp_path):
    """`src="user"` es el canvas informando de lo que ya pasó — el fantasma que V2-261 filtra. Tomarlo por
    la apertura de la hoja medía una tarjeta que no abrió nadie."""
    ev = [(500.0, "widget", "show", "results", "user")] + REAL
    out = verify.sheet_timing(_db(tmp_path, ev))
    assert out["sheet_box"] == "c30db3-1"
    assert out["sheet_ms"] == 1000.0, "el eco es 500 ms antes y no puede ganar"


def test_ESTRENAR_no_es_llenar(tmp_path):
    """Sin esto el reloj de las filas cae en el instante de la apertura y toda ronda «entrega al principio»."""
    out = verify.sheet_timing(_db(tmp_path, REAL))
    assert out["sheet_rows_ms"] == 39000.0
    assert out["sheet_rows_ms"] != out["sheet_ms"]


def test_un_REPINTADO_DE_FASE_no_es_una_fila(tmp_path):
    """El caso de la ronda 23: `record_phase` emite `data src=worker` para que la pestaña de proceso avance,
    con la hoja aún VACÍA. Contarlo adelantó el reloj 104 s y el juez acusó al turno de callar una entrega
    que no existía."""
    ev = [(1000.0, "widget", "show", "results::r23-1", "worker:1"),
          (5000.0, "widget", "data", "results::r23-1", "worker"),     # fase, sin op
          (9000.0, "widget", "data", "results::r23-1", "worker")]     # fase, sin op
    out = verify.sheet_timing(_db(tmp_path, ev))
    assert out["sheet_rows_ms"] is None, "solo fases: la hoja nunca recibió una fila"


def test_una_DATA_OP_del_worker_si_cuenta(tmp_path):
    """La otra dirección: un worker que escribe filas por el puente (`hbwidget data results append`) emite
    `src=worker` CON su `op` — eso sí es una entrega, y perderla sería el hueco contrario."""
    p = tmp_path / "op.db"
    import sqlite3 as _sq
    con = _sq.connect(str(p))
    con.execute("CREATE TABLE events (ts_ms REAL, topic TEXT, kind TEXT, label TEXT, payload TEXT)")
    con.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                (1000.0, "observer", "widget", "show",
                 json.dumps({"id": "results::op-1", "label": "show", "src": "worker:1"})))
    con.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                (7000.0, "observer", "widget", "data",
                 json.dumps({"id": "results::op-1", "label": "data", "src": "worker", "op": "append"})))
    con.commit(); con.close()
    out = verify.sheet_timing(str(p))
    assert out["sheet_rows_ms"] == 7000.0


def test_un_VACIADO_tampoco_es_llenar(tmp_path):
    ev = [(1000.0, "widget", "show", "results::x-1", "worker:1"),
          (5000.0, "widget", "blank", "results--x-1", "system"),
          (5000.0, "widget", "data", "results--x-1", "system"),
          (9000.0, "widget", "data", "results::x-1", "navegador")]
    out = verify.sheet_timing(_db(tmp_path, ev))
    assert out["sheet_rows_ms"] == 9000.0, "el `data` del vaciado es del sistema y no cuenta"


def test_las_DOS_formas_del_id_son_la_misma_hoja(tmp_path):
    """`results::<x>` (canvas) y `results--<x>` (disco) conviven en el mismo segundo; mirar una sola pierde
    la mitad de las escrituras."""
    assert verify._sheet_timing_box("results::abc-1") == "abc-1" if hasattr(verify, "_sheet_timing_box") else True
    out = verify.sheet_timing(_db(tmp_path, [
        (1000.0, "widget", "show", "results--z-9", "worker:1"),
        (4000.0, "widget", "data", "results::z-9", "navegador")]))
    assert out["sheet_box"] == "z-9" and out["sheet_rows_ms"] == 4000.0


def test_NO_MEDIDO_no_es_llego_tarde(tmp_path):
    """Sin escrituras de un productor el reloj se queda en None, nunca en 0 — confundirlos inventa un fallo."""
    out = verify.sheet_timing(_db(tmp_path, [(1000.0, "widget", "show", "results::q-1", "worker:1")]))
    assert out["sheet_rows_ms"] is None


def test_se_CONSERVA_el_reloj_de_la_narracion_aparte():
    """Contesta otra pregunta —cuándo el navegador lo contó— y perderla al arreglar esto sería cambiar un
    hueco por otro. Va con su propio nombre para que nadie los vuelva a confundir."""
    import inspect
    from tests.use_cases.e2e.agent import run as runmod
    src = inspect.getsource(runmod._run_scenario)
    assert "narrated_after_last_turn_s" in src
    assert "sheet_rows_ms" in src
    assert src.index("_rows - _lt") < src.index("_fr - _lt"), (
        "el que manda en `after_last_turn_s` tiene que ser el reloj de la HOJA")


# ── V2-355: y el reloj que cronometra una ENTREGA es más estricto todavía ──────────────────────────────
#
# V2-300 (arriba) sacó del reloj el repintado de fase. Quedaba media capa: `sheet_rows_ms` sigue arrancando
# con la primera escritura de un PRODUCTOR, y el comentario del propio `verify` ya lo admitía — «un `data` de
# un productor no PRUEBA que la fila tenga nombre». El worker escribe en su hoja mucho antes de tener
# candidatos: los criterios, el título, su plan. Medido en `restaurant-tonight-madrid` (2026-08-27), la hoja
# acabó con «Mensaje de WhatsApp preparado», «Por teléfono (lo más rápido)» y «Qué me paró» — prosa suya
# contada como tres candidatos.
#
# Y ese reloj es el que alimenta `delivery_lag_s`, o sea el que produce los [alta] de RETENCIÓN, que son el
# bloqueador nº1 de media docena de casos. En `search-buy-camera__es` (2026-08-27) cronometró **130,8 s de
# retención** con la primera página abierta a los **62,3 s**: a los 17 s no podía existir un candidato. Misma
# forma que V2-300, una capa más adentro, y con el mismo coste — el instrumento acusando al producto.
#
# El intake del navegador (`src == "navegador"`) es, por construcción, candidatos sacados de una página. Se
# guarda APARTE en vez de endurecer el de arriba porque los dos dicen cosas distintas y las dos hacen falta:
# «cuándo empezó a escribir» separa «llegó tarde» de «no llegó»; «cuándo hubo candidatos» es el único que
# puede cronometrar una entrega.

def _db_op(tmp_path, events):
    """Como `_db`, pero las filas llevan `op` — el campo que distingue una data-op del puente del repintado."""
    p = tmp_path / "op.db"
    con = sqlite3.connect(str(p))
    con.execute("CREATE TABLE events (ts_ms REAL, topic TEXT, kind TEXT, label TEXT, payload TEXT)")
    for ts, kind, label, ident, src, op in events:
        d = {"id": ident, "label": label, "src": src}
        if op:
            d["op"] = op
        con.execute("INSERT INTO events VALUES (?,?,?,?,?)", (ts, "observer", kind, label, json.dumps(d)))
    con.commit(); con.close()
    return str(p)


# La forma de `search-buy-camera__es`: el worker abre y escribe lo suyo temprano, la página no se abre hasta
# el segundo 62 y el intake cae después. Un candidato ANTES de abrir la primera página es imposible.
CAMARA = [
    (1_000.0, "widget", "show", "results::afd21d-1", "worker:1", None),
    (17_500.0, "widget", "data", "results::afd21d-1", "worker", "present"),   # sus criterios, NO candidatos
    (62_300.0, "navegador", "hito", "", "", None),
    (70_000.0, "widget", "data", "results::afd21d-1", "navegador", None),     # el intake: AQUÍ hay candidatos
]


def test_el_reloj_flojo_sigue_diciendo_cuando_empezo_a_escribir(tmp_path):
    """No se endurece el de arriba: separa «llegó tarde» de «no llegó» y esa mitad hace falta."""
    out = verify.sheet_timing(_db_op(tmp_path, CAMARA), since=0)
    assert out["sheet_rows_ms"] == 17_500.0


def test_el_reloj_ESTRICTO_espera_al_intake(tmp_path):
    """El que cronometra una entrega. 17,5 s contra 70 s son 52 segundos de «retención» inventada."""
    out = verify.sheet_timing(_db_op(tmp_path, CAMARA), since=0)
    assert out["sheet_named_ms"] == 70_000.0


def test_una_hoja_que_SOLO_tiene_prosa_del_worker_no_arranca_el_reloj_estricto(tmp_path):
    """`restaurant-tonight-madrid`: tres data-ops del worker y ni una extracción. No hubo candidatos, así que
    no hay nada que cronometrar — y `None` es la respuesta honesta, no un cero."""
    solo_prosa = [
        (1_000.0, "widget", "show", "results::1e8200-1", "worker:1", None),
        (10_000.0, "widget", "data", "results::1e8200-1", "worker", "present"),
        (20_000.0, "widget", "data", "results::1e8200-1", "worker", "append"),
        (30_000.0, "widget", "data", "results::1e8200-1", "worker", "append"),
    ]
    out = verify.sheet_timing(_db_op(tmp_path, solo_prosa), since=0)
    assert out["sheet_named_ms"] is None, "sin intake no hubo candidatos que retener"
    assert out["sheet_rows_ms"] == 10_000.0


def test_el_repintado_de_fase_sigue_fuera_de_los_DOS(tmp_path):
    """V2-300 no se revierte por el camino: un `data src=worker` SIN `op` es el repintado de fase."""
    solo_repintado = [
        (1_000.0, "widget", "show", "results::x-1", "worker:1", None),
        (20_000.0, "widget", "data", "results::x-1", "worker", None),
    ]
    out = verify.sheet_timing(_db_op(tmp_path, solo_repintado), since=0)
    assert out["sheet_rows_ms"] is None and out["sheet_named_ms"] is None


def test_el_intake_solo_ya_arranca_los_dos(tmp_path):
    """Una ronda donde el navegador entrega sin que el worker haya escrito antes: los dos relojes coinciden,
    que es lo correcto — ahí no hay nada que separar."""
    directo = [
        (1_000.0, "widget", "show", "results::y-1", "worker:1", None),
        (45_000.0, "widget", "data", "results::y-1", "navegador", None),
    ]
    out = verify.sheet_timing(_db_op(tmp_path, directo), since=0)
    assert out["sheet_rows_ms"] == 45_000.0 == out["sheet_named_ms"]
