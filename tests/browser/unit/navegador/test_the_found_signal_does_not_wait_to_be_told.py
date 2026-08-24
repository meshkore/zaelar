"""La señal de «ya encontró algo» era un REPORTE VOLUNTARIO, y el worker no siempre lo hace (V2-284).

Medido en la tanda del 2026-08-24 03:02, leyendo los prompts de los DIEZ turnos de
`search-secondhand-monitor__es`: la cara no salió ni una sola vez. La línea del navegador decía

    «Busca en marketplaces de segunda mano (Wallapop, etc.) un monitor de a» — en es.wallapop.com, 1 pasos dados

y nada más, en los diez, mientras el mecanismo de esa misma ronda registraba **11 navegaciones, 5
extracciones** y monitores reales con precio y enlace (MSI MAG 70 €, Dell P2714H 60 €, BenQ 60 €). El mismo
silencio en TRES de los cuatro casos de la tanda, y el veredicto de los tres fue el mismo: «tuvo resultados
reales del worker y no los entregó». El juez tenía razón en el hecho y se equivocaba de culpable: al prompt
del turno no llegó nunca que hubiera algo.

La causa: `_found_candidates` leía SOLO `rec.kept`, que existe si el worker se acordó de llamar a
`hbnote considered --kept N`. Un reporte que hay que acordarse de hacer no es una señal, es una cortesía.

Las filas de la hoja son un hecho que no depende de que nadie se acuerde: las escribe `intake.push` cuando el
navegador extrae (V2-257). Y se leen por la PESTAÑA, no por el registro de sesiones vivas, porque el momento
en que esto más falta hace es justo cuando el worker ya no está (V2-281).
"""
import pytest

from nucleo.flash import live_blocks as LB
from widgets.navegador import tasks as T
from widgets.results import data as SHEET


@pytest.fixture(autouse=True)
def _clean():
    T._tasks.clear()
    yield
    T._tasks.clear()


def _sheet_with(sheet: str, titles: list[str]):
    SHEET.apply_action("present", {"sheet": sheet, "title": "Resultados",
                                   "items": [{"title": t, "price": "70 €"} for t in titles]})


def test_la_cara_dispara_con_las_filas_de_la_hoja_sin_que_el_worker_avise():
    tid = T.create("Busca un monitor de segunda mano", sheet="v284-1")
    _sheet_with("v284-1", ["MSI MAG 276CXF 27 280Hz Gaming Monitor"])
    assert LB._found_candidates(tid) is True


def test_y_ese_era_el_agujero_sin_hoja_no_hay_nada_que_leer():
    """Sensibilidad: con la hoja vacía la cara sigue callada, que es lo correcto."""
    tid = T.create("Busca un monitor de segunda mano", sheet="v284-vacia")
    assert LB._found_candidates(tid) is False


def test_una_fila_SIN_nombre_no_es_un_resultado():
    """Misma regla que la nota del navegador (V2-234): un enlace que estaba en la página no es un hallazgo.

    ⚠️ Y quien la aplica de verdad es LA HOJA, no este predicado: `apply_action` descarta la fila sin título
    al entrar — medido aquí abajo. O sea que el filtro de `_sheet_has_rows` es hoy un cinturón sobre unos
    tirantes, y se dice porque un test que afirma cubrir algo que la capa de al lado ya garantiza es un test
    que MIENTE sobre su cobertura (el desarme lo enseñó: quitar el filtro no ponía rojo nada).
    """
    tid = T.create("Busca un monitor", sheet="v284-2")
    SHEET.apply_action("present", {"sheet": "v284-2", "title": "Resultados",
                                   "items": [{"title": "", "url": "https://x.example/categoria"}]})
    assert (SHEET.view_data("v284-2") or {}).get("items") == [], (
        "la hoja dejó de descartar la fila sin nombre: ahora el filtro de `_sheet_has_rows` SÍ es el mecanismo")
    assert LB._found_candidates(tid) is False


def test_una_pestana_SIN_encargo_detras_no_mira_ninguna_hoja():
    """El operador conduciendo el navegador a mano: sin sello, no hay hoja del encargo que consultar.

    La caja PELADA se llena a propósito en este caso, que es lo que lo hace morder: sin la guarda,
    `view_data("")` la lee y la cara dispararía con los restos de OTRA ronda — 38 filas acumuladas medidas en
    la tanda del 2026-08-24. Un fantasma con forma de hallazgo.
    """
    SHEET.apply_action("present", {"sheet": "", "title": "Resultados",
                                   "items": [{"title": "Guitarra de otra ronda", "price": "100 €"}]})
    assert (SHEET.view_data("") or {}).get("items"), "la caja de nadie tiene que estar llena para que muerda"
    assert LB._found_candidates(T.create("el operador abre una web")) is False


def test_el_reporte_del_worker_SIGUE_valiendo():
    """No se sustituye una señal por otra: `kept` llega antes que la hoja cuando el worker sí avisa."""
    from nucleo import dispatch as D
    from nucleo.workers.session import SessionRecord
    tid = T.create("Busca un monitor", sheet="v284-3")
    rec = SessionRecord(task_id="w1", goal="Busca un monitor", kind="web")
    rec.nav_task, rec.kept, rec.status = tid, 4, "running"
    D._SESSIONS.clear()
    D._SESSIONS["w1"] = rec
    try:
        assert LB._found_candidates(tid) is True      # con la hoja todavía vacía
    finally:
        D._SESSIONS.clear()


def test_y_la_cara_LLEGA_al_estado_cuando_la_hoja_tiene_filas():
    """La mitad de cableado: que el hecho salga en el bloque que el turno lee, no solo en el predicado.

    Un arreglo cuyo predicado acierta y cuyo bloque no lo enseña pasa sus tests y no cambia nada (V2-199).
    """
    tid = T.create("Busca un monitor de segunda mano", sheet="v284-4")
    T.set_status(tid, "working")
    _sheet_with("v284-4", ["Monitor Dell 27 P2714H LED"])
    state = "\n".join(LB.navegador_lines())
    assert "YA HA ENCONTRADO ALGO" in state
    assert "CUÉNTASELO en este turno" in state
