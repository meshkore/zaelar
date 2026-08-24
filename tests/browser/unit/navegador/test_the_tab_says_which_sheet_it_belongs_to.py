"""La pestaña DICE de qué hoja es — si no, dos diagnósticos opuestos se leen igual (2026-08-24).

`create()` sella la hoja del encargo en la pestaña desde V2-281, y ese sello es por donde
`nucleo/flash/live_blocks.py::_sheet_has_rows` resuelve si el encargo ya tiene filas. Sin sello contesta
False por muchas filas que haya, y el turno sigue diciendo «todavía no tengo nada» mientras el operador ve
caer los resultados — medido hoy en tres casos: la hoja se llenó 42, 49 y 113 s ANTES del último turno.

El sello vivía solo dentro del proceso. Desde fuera, «la pestaña nunca se selló» y «se selló y algo río
abajo lo ignoró» daban EXACTAMENTE la misma lectura, y elegir mal cuesta una tanda entera midiendo la mitad
equivocada. Es el mismo hueco que V2-207 cerró con `wall`/`walls_hit`, por la misma razón.

Esto NO arregla la entrega: hace que la pregunta se pueda contestar desde cualquier informe.
"""
from widgets.navegador import data as navdata
from widgets.navegador import tasks as navtasks


def test_la_vista_dice_de_que_hoja_es_la_pestana():
    tid = navtasks.create("busca una guitarra", sheet="results::abc-1")
    try:
        assert navdata._task_view(navtasks.get(tid))["sheet"] == "results::abc-1"
    finally:
        navtasks.drop(tid) if hasattr(navtasks, "drop") else None


def test_una_pestana_SIN_encargo_dice_que_no_tiene_hoja():
    """Vacío es la respuesta correcta, no un fallo: una pestaña que abre el operador a mano no tiene encargo
    detrás, así que no tiene hoja propia. Lo que no puede es ser indistinguible de una que sí lo tenía."""
    tid = navtasks.create("el operador navegando a mano")
    try:
        assert navdata._task_view(navtasks.get(tid))["sheet"] == ""
    finally:
        navtasks.drop(tid) if hasattr(navtasks, "drop") else None


def test_el_sello_lo_pone_QUIEN_abre_el_encargo():
    """Guarda de cableado. `_prepare_web` es el único que lo pasa hoy, y si deja de hacerlo `_sheet_has_rows`
    se queda ciega sin que falle nada — el modo de fallo que este campo existe para hacer visible."""
    import inspect
    from nucleo import dispatch
    src = "\n".join(l for l in inspect.getsource(dispatch._prepare_web).splitlines()
                    if not l.strip().startswith("#"))
    assert "sheet=sheet_of(rec)" in src, (
        "la pestaña del encargo tiene que nacer sellada; sin sello, el turno no puede ver su propia hoja")
