"""Una PESTAÑA sobrevive al worker que la abrió, y su hoja se resolvía por el registro de los vivos (V2-281).

Medido en `search-secondhand-monitor__es` (2026-08-24 01:47), la ronda que aprobó:

    por encargo: results: 24 fila(s) «Resultados» · results::9fc24a-1: 12 fila(s) «Busca un monitor…»

UN encargo, y sus hallazgos partidos en dos cajas — con la MAYORÍA en la hoja PELADA, que desde V2-259 no es
de nadie. Y esa caja huérfana es además la «TARJETA FANTASMA» que el canvas lleva rondas reportando.

La causa: `act_api._sheet_of` resolvía con `dispatch.sheet_for_nav_task`, que recorre `_SESSIONS` — el
registro de sesiones VIVAS. Pero una pestaña dura más que su worker: el record se saca en el `finally` de
`_run_session`, y un relevo de proveedor (V2-238) abre un worker nuevo. Así que todo hallazgo que llegue
después de esa muerte resolvía a "" y caía en la hoja de siempre.

Es la MISMA forma que V2-108 con el `trace`: un hecho que el llamante tiene al crear la pestaña y que el
registro no puede contestar más tarde. Mismo remedio: se sella al nacer.
"""
import pytest

from widgets.navegador import act_api
from widgets.navegador import tasks as T


@pytest.fixture(autouse=True)
def _clean():
    T._tasks.clear()
    yield
    T._tasks.clear()


def test_la_pestana_guarda_la_hoja_de_su_encargo():
    tid = T.create("Busca un monitor de segunda mano", sheet="9fc24a-1")
    assert T.get(tid)["sheet"] == "9fc24a-1"
    assert act_api._sheet_of(tid) == "9fc24a-1"


def test_y_la_conserva_cuando_su_worker_YA_NO_ESTA():
    """El caso medido: el record murió (relevo) y el hallazgo llega después."""
    from nucleo import dispatch as D
    tid = T.create("Busca un monitor de segunda mano", sheet="9fc24a-1")
    D._SESSIONS.clear()                       # el worker se murió y `_run_session` sacó su record
    assert D.sheet_for_nav_task(tid) == "", "el registro de vivos ya no puede contestar — ése era el agujero"
    assert act_api._sheet_of(tid) == "9fc24a-1", "el hallazgo tardío vuelve a caer en la hoja de nadie"


def test_una_pestana_SIN_encargo_sigue_entregando_en_la_hoja_de_siempre():
    """El operador conduciendo el navegador a mano: no hay encargo, así que no hay instancia. Es lo correcto,
    y convertirlo en un id inventado sería peor que el defecto."""
    assert act_api._sheet_of(T.create("el operador abre una web")) == ""


def test_el_registro_de_sesiones_sigue_siendo_el_RESPALDO():
    """Una pestaña creada ANTES de este cambio no lleva sello, y mientras su worker viva el registro sí sabe.

    Sin esta mitad, «arreglar» la resolución la rompería para todo lo que ya estaba abierto.
    """
    from nucleo import dispatch as D
    from nucleo import surfaces
    from nucleo.workers.session import SessionRecord
    tid = T.create("Busca un monitor")                    # sin sello, como las de antes
    rec = SessionRecord(task_id="w9", goal="Busca un monitor", kind="web")
    surfaces.set_once(rec, "lista")
    rec.status, rec.nav_task, rec.sheet = "running", tid, "viejo-1"
    D._SESSIONS.clear()
    D._SESSIONS["w9"] = rec
    try:
        assert act_api._sheet_of(tid) == "viejo-1"
    finally:
        D._SESSIONS.clear()


def test_el_sello_lo_PONE_quien_prepara_la_pestana():
    """La mitad que ninguna medición del módulo ve: que `_prepare_web` se lo pase de verdad.

    Es la lección de V2-199 — un arreglo cuyo dato nunca se escribe pasa sus tests y no hace nada.
    """
    import inspect

    from nucleo import dispatch as D
    src = inspect.getsource(D._prepare_web)
    assert "sheet=sheet_of(rec)" in src, "la pestaña vuelve a nacer sin saber de qué encargo es"
