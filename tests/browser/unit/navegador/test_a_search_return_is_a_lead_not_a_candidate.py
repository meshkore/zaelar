"""Lo que vuelve de una búsqueda web es una PISTA, no un candidato (V2-376).

Medido en `weekend-adventure-sports-bilbao__es` (2026-08-27, 2/5): **52 «candidatos con nombre»** en la hoja,
de UNA sola fuente, y sus títulos eran páginas:

    «Descensos de Barranquismo en Vizcaya: 9 precios y ofertas 2026»
    «Bilbao despliega ocho escenarios de música gratis en Aste Nagusia 2026»
    «Top actividad en Bilbao - Reserva con cancelación gratis»
    «Viajes, tours, entradas y más - Excursiones Fuera De Bilbao»

Ninguna es una actividad: son una comparativa, una noticia y dos portadas. La misma forma que los ocho
títulos de Google que se contaron como coches de alquiler el mismo día.

**V2-320 NO se deshace, y es lo que hay que conservar**: buscar es una forma legítima de resolver
«actividades cerca de X», y aquella iniciativa existe porque un encargo resuelto SOLO por búsqueda dejaba la
hoja vacía 709 segundos. Lo que faltaba no era la puerta: era que la fila DIGA lo que es.

Llamarla «SIN PRECIO» —la etiqueta de V2-360— la presenta como una ficha a la que le falta un dato, que es
justo la sustitución que hace que acaben ofreciéndose «9 precios y ofertas 2026» como un plan. La marca viaja
por `facts`, vocabulario que la hoja ya conserva (es por donde va el teléfono), así que no toca el contrato
del widget.
"""
import pytest

from nucleo.flash import live_blocks as LB
from nucleo.workers import findings as F
from widgets.navegador import tasks as T
from widgets.results import data as SHEET
from widgets.results import intake as IN

MEDIDO = {"source": "brave", "results": [
    {"title": "Descensos de Barranquismo en Vizcaya: 9 precios y ofertas 2026",
     "snippet": "Compara precios", "url": "https://x.invalid/a"},
    {"title": "Bilbao despliega ocho escenarios de música gratis en Aste Nagusia 2026",
     "snippet": "Noticia", "url": "https://x.invalid/b"},
]}


@pytest.fixture
def tarea():
    tid = T.create("deportes de aventura cerca de Bilbao para el finde", sheet="v376-hoja")
    yield tid
    T._tasks.clear()


class _Rec:
    sheet = "v376-hoja"


def _sembrar(items):
    SHEET.apply_action("present", {"sheet": "v376-hoja", "title": "Resultados", "items": items})


# ── la marca nace en la puerta de la búsqueda ──────────────────────────────────────────────────────────────

def test_una_vuelta_de_busqueda_entra_MARCADA():
    _sembrar([])
    assert F.hand_search_rows(_Rec(), MEDIDO) == 2
    items = (SHEET.view_data("v376-hoja") or {}).get("items") or []
    assert len(items) == 2
    for it in items:
        assert {"label": "Origen", "value": "búsqueda web"} in (it.get("facts") or [])


def test_V2_320_SIGUE_EN_PIE_las_filas_entran(tarea):
    """La razón de ser de V2-320: un encargo resuelto solo por búsqueda no puede dejar la hoja vacía."""
    _sembrar([])
    assert F.hand_search_rows(_Rec(), MEDIDO) > 0
    assert (SHEET.view_data("v376-hoja") or {}).get("items")


def test_una_vuelta_SIN_titulos_no_entra():
    _sembrar([])
    assert F.hand_search_rows(_Rec(), {"results": [{"title": "", "url": "u"}]}) == 0


# ── y el turno la lee como lo que es ───────────────────────────────────────────────────────────────────────

def test_la_cara_NO_la_llama_candidato_sin_precio(tarea):
    _sembrar([{"title": "Descensos de Barranquismo en Vizcaya: 9 precios y ofertas 2026",
               "url": "https://x.invalid/a", "facts": [{"label": "Origen", "value": "búsqueda web"}]}])
    (fila,) = LB._sheet_top_rows(tarea, 5)
    assert "SIN PRECIO" not in fila
    assert "PÁGINA WEB por mirar" in fila and "aún no es un candidato" in fila


def test_una_ficha_CON_precio_no_cambia(tarea):
    """Sensibilidad: la marca no puede tocar a las fichas de verdad."""
    _sembrar([{"title": "Tour en kayak por Bilbao", "price": "35 €", "url": "https://x.invalid/b"}])
    assert LB._sheet_top_rows(tarea, 5) == ["«Tour en kayak por Bilbao — 35 €»"]


def test_una_ficha_SIN_precio_y_SIN_marca_sigue_diciendo_SIN_PRECIO(tarea):
    """V2-360 intacto: una aseguradora sin importe sigue teniendo que decir que no lo trae."""
    _sembrar([{"title": "Allianz Direct", "url": "https://x.invalid/c"}])
    (fila,) = LB._sheet_top_rows(tarea, 5)
    assert "SIN PRECIO" in fila


# ── y de paso, una rama que estaba MUERTA ──────────────────────────────────────────────────────────────────

def test_el_TELEFONO_por_fin_llega_a_la_cara(tarea):
    """V2-360 leía `item["tel"]`, y `intake._to_item` guarda el teléfono en `facts` como «Teléfono» — o sea
    que para CUALQUIER fila que pasara por la puerta compartida esa rama no se ejecutaba nunca y el fontanero
    salía «SIN PRECIO» teniendo su número dentro. Verificado antes de afirmarlo: la hoja no conserva ninguna
    clave `tel`."""
    _sembrar([{"title": "Fontaneros 24H Bilbao",
               "facts": [{"label": "Teléfono", "value": "944123456"}], "url": "https://x.invalid/d"}])
    it = ((SHEET.view_data("v376-hoja") or {}).get("items") or [{}])[0]
    assert it.get("tel") is None, "premisa: la hoja no guarda una clave `tel`"
    (fila,) = LB._sheet_top_rows(tarea, 5)
    assert "944123456" in fila


def test_el_TELEFONO_gana_a_la_marca_de_pista(tarea):
    """Un número al que llamar es accionable (V2-240); la procedencia no lo deja de serlo."""
    _sembrar([{"title": "Escuela de surf Sopelana", "url": "https://x.invalid/e",
               "facts": [{"label": "Teléfono", "value": "944999888"},
                         {"label": "Origen", "value": "búsqueda web"}]}])
    (fila,) = LB._sheet_top_rows(tarea, 5)
    assert "944999888" in fila and "PÁGINA WEB" not in fila


def test_la_puerta_conserva_el_telefono_Y_la_marca():
    """`_to_item` construía `facts` desde cero con el teléfono, así que unas `facts` que llegaran en la fila
    se perdían enteras."""
    it = IN._to_item({"title": "Cosa", "tel": "600111222",
                      "facts": [{"label": "Origen", "value": "búsqueda web"}]})
    etiquetas = [f["label"] for f in it["facts"]]
    assert "Teléfono" in etiquetas and "Origen" in etiquetas
