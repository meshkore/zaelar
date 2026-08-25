"""¿Reseteó alguien el motor mientras se medía esta ronda? Un hecho de ATRIBUCIÓN, no un veredicto.

`started_at` se sella DENTRO de `_run_scenario`, después del `hard_reset()` de la propia tanda, así que un
`session/RESET` posterior vino de otro sitio — una segunda tanda, o el operador tocando el plató.

Importa porque un reset cierra TODAS las tarjetas (`emit("widget","close")` → `owner._close_task`), y cerrar una
tarjeta con su tarea viva deja la pestaña en `cancelled` SIN tocar al worker. Que es exactamente la firma de la
familia archivada como «cancelación a mitad con el navegador en la página buena» (3 de 28 rondas, 2026-08-25):
`navegador_task.status == 'cancelled'` con `worker_health.cancelled == 0`. La pregunta nunca fue «qué cancela
pestañas» sino «quién reseteó el motor», y el informe no tenía con qué contestarla.
"""
import json
import sqlite3

import pytest

from tests.use_cases.e2e.agent import verify as V


@pytest.fixture
def db(tmp_path):
    """Un test unitario nunca toca el sandbox vivo."""
    p = tmp_path / "obs.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, ts_ms INTEGER, topic TEXT, payload TEXT, "
                "cat TEXT, kind TEXT, label TEXT)")

    def add(*, ts, cat="sistema", kind="session", label="RESET"):
        con.execute("INSERT INTO events (ts_ms, topic, payload, cat, kind, label) VALUES (?,?,?,?,?,?)",
                    (int(ts * 1000), "obs", json.dumps({}), cat, kind, label))
    con.commit()
    return p, con, add


def test_una_ronda_limpia_no_acusa_a_nadie(db):
    p, con, add = db
    add(ts=100.0, label="turn")
    con.commit()
    assert V.resets_during_round(str(p), since=1000.0) == {"n": 0, "at_s": []}


def test_el_reset_de_la_PROPIA_tanda_queda_fuera(db):
    """La sensibilidad que hace útil al instrumento: `hard_reset()` corre ANTES de sellar `started_at`, así que
    contarlo marcaría todas las rondas y el hecho no distinguiría nada."""
    p, con, add = db
    add(ts=990.0)            # el reset del propio caso, justo antes de empezar
    con.commit()
    assert V.resets_during_round(str(p), since=1000.0)["n"] == 0


def test_un_reset_AJENO_se_ve_y_dice_CUÁNDO(db):
    """El segundo es tan importante como el primero: un reset a los 12 s tira la ronda entera; uno a los 400 s
    puede haber caído después de la entrega que importaba."""
    p, con, add = db
    add(ts=1012.5)
    con.commit()
    r = V.resets_during_round(str(p), since=1000.0)
    assert r["n"] == 1
    assert r["at_s"] == [12.5]


def test_cuenta_TODOS_los_ajenos(db):
    p, con, add = db
    for t in (1010.0, 1200.0, 1305.0):
        add(ts=t)
    con.commit()
    assert V.resets_during_round(str(p), since=1000.0)["n"] == 3


def test_lo_encuentra_aunque_la_FAMILIA_cambie_de_nombre(db):
    """Una señal buscada por el campo equivocado vuelve a CERO, y un cero se lee como «esto no pasó» — la forma
    más silenciosa que tiene un instrumento de mentir."""
    p, con, add = db
    add(ts=1050.0, cat="otra-cosa", kind="lo-que-sea")
    con.commit()
    assert V.resets_during_round(str(p), since=1000.0)["n"] == 1


def test_una_db_que_no_existe_no_revienta_la_ronda():
    assert V.resets_during_round("/no/such/place.db", since=1.0) == {"n": 0, "at_s": []}


def test_el_informe_LO_LLEVA():
    """La mitad de cableado (V2-199): el hecho puede leerse bien y no llegar a quien lo necesita."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    assert 'mech["resets_during_round"] = verifymod.resets_during_round(' in inspect.getsource(R._run_scenario)
