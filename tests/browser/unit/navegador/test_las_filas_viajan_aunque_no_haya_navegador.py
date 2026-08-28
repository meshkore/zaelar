"""V2-451 · el bloque de filas colgaba de la PESTAÑA, así que un encargo sin navegador no enseñaba ninguna.

`_sheet_top_rows` resuelve la hoja DESDE la tarea de navegador, y `navegador_lines()` solo compone caras si
hay tareas. Un encargo resuelto por BÚSQUEDA no tiene pestaña: llena la hoja y el prompt no nombra una sola
fila — y ni siquiera se emite el aviso de V2-438, porque vive dentro de la función que nadie llama.

Medido en `cheapest-monitor__us` (2026-08-28, plató 24/7):

    navegador_task_id: ""            ← no hubo navegador en toda la ronda
    results_sheet: 6 filas con nombre y precio (Dell S2725QC, LG 27UP650-W, BenQ GW2790QT…)
    delivery_completeness: {named: 0, available: 6, shown_to_model: false}
    unresolved_errand_sheets: TODO a cero — ni un aviso

y el juez de bloqueador: «respondió con una promesa vacía ("I'll get back to you") sin entregar nada. La hoja
de resultados ya tenía 6». Es la causa que quedaba abierta desde V2-432, V2-441 y V2-444: la hoja es del
ENCARGO (V2-259) y el prompt solo sabía leerla por el navegador.
"""
import pytest

from nucleo import dispatch as D
from nucleo.flash import live_blocks as LB
from nucleo.workers.session import SessionRecord
from widgets.navegador import tasks as T
from widgets.results import data as SHEET


@pytest.fixture(autouse=True)
def _clean():
    T._tasks.clear()
    D._SESSIONS.clear()
    yield
    T._tasks.clear()
    D._SESSIONS.clear()


def _encargo_sin_navegador(sheet="v451-1", filas=(("Dell S2725QC", "$280"), ("LG 27UP650-W", "$230"))):
    rec = SessionRecord(task_id="w1", goal="cheapest 4K monitor", kind="web")
    rec.status, rec.sheet = "running", sheet
    D._SESSIONS["w1"] = rec
    if filas:
        SHEET.apply_action("present", {"sheet": sheet, "title": "Resultados",
                                       "items": [{"title": t, "price": p} for t, p in filas]})
    return rec


def test_las_filas_de_su_hoja_llegan_al_prompt_SIN_pestana_de_navegador():
    _encargo_sin_navegador()
    st = "\n".join(LB.pending_task_lines())
    assert "YA ENTREGADO (de su hoja)" in st
    assert "Dell S2725QC — $280" in st and "LG 27UP650-W — $230" in st
    assert not T._tasks, "la premisa del caso es que NO hay tarea de navegador"


def test_sin_filas_no_se_dice_nada():
    """Un bloque que sale siempre deja de leerse, y anunciar una entrega vacía es la mentira de V2-209."""
    # Hoja PROPIA: el almacén se comparte entre tests, así que reusar la del caso anterior lee sus filas y el
    # test falla por el motivo equivocado — comprobado, falló así al escribirlo.
    _encargo_sin_navegador(sheet="v451-vacia", filas=())
    assert "YA ENTREGADO (de su hoja)" not in "\n".join(LB.pending_task_lines())


def test_sin_hoja_sellada_no_se_inventa_ninguna():
    """Un encargo sin hoja lee la caja PELADA si se le deja, y ésa es el cementerio de rondas anteriores
    (V2-281): enseñaría hallazgos de OTRO encargo como si fueran de éste."""
    rec = SessionRecord(task_id="w1", goal="algo", kind="web")
    rec.status, rec.sheet = "running", ""
    D._SESSIONS["w1"] = rec
    SHEET.apply_action("present", {"sheet": "", "title": "Resultados",
                                   "items": [{"title": "Guitarra de otra ronda", "price": "100 €"}]})
    st = "\n".join(LB.pending_task_lines())
    assert "Guitarra de otra ronda" not in st


def test_una_fila_SIN_precio_lo_dice_en_vez_de_callarlo():
    """Misma regla que `_sheet_top_rows` (V2-360): nombrar el hueco cuesta una palabra y cierra la
    sustitución — un nombre a secas se lee como una opción comparable."""
    _encargo_sin_navegador(filas=(("Monitor sin importe", ""),))
    assert "SIN PRECIO" in "\n".join(LB.pending_task_lines())


def test_el_resumen_del_encargo_LLEVA_su_hoja():
    """La fontanería: sin el campo en `pending_summaries`, el bloque no tiene con qué leer y los cuatro de
    arriba pasarían con el arreglo a medias."""
    rec = _encargo_sin_navegador()
    fila = next(x for x in D.pending_summaries() if x["id"] == "w1")
    assert fila.get("sheet") == rec.sheet
