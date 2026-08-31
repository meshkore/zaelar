"""What comes back from a web search is a LEAD, not a candidate (V2-376).

Measured in `weekend-adventure-sports-bilbao__es` (2026-08-27, 2/5): **52 “named candidates”** in the sheet,
from a SINGLE source, and their titles were pages:

    «Descensos de Barranquismo en Vizcaya: 9 precios y ofertas 2026»
    «Bilbao despliega ocho escenarios de música gratis en Aste Nagusia 2026»
    «Top actividad en Bilbao - Reserva con cancelación gratis»
    «Viajes, tours, entradas y más - Excursiones Fuera De Bilbao»

None is an activity: they are a comparison, a news article, and two homepages. The same way that the eight
Google titles counted as rental cars on the same day were.

**V2-320 is NOT being undone, and that is what must be preserved**: searching is a legitimate way to resolve
“activities near X”, and that initiative exists because a request resolved ONLY by search left the sheet
empty for 709 seconds. What was missing was not the doorway: it was for the row to SAY what it is.

Calling it “NO PRICE” —the V2-360 label— presents it as a listing missing a piece of data, which is
exactly the substitution that causes “9 prices and offers 2026” to end up being offered as a plan. The mark
travels through `facts`, vocabulary that the sheet already preserves (that is where the phone number goes),
so it does not affect the widget contract.
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


# ── the mark is created at the search doorway ──────────────────────────────────────────────────────────────

def test_una_vuelta_de_busqueda_entra_MARCADA():
    _sembrar([])
    assert F.hand_search_rows(_Rec(), MEDIDO) == 2
    items = (SHEET.view_data("v376-hoja") or {}).get("items") or []
    assert len(items) == 2
    for it in items:
        assert {"label": "Origen", "value": "búsqueda web"} in (it.get("facts") or [])


def test_V2_320_SIGUE_EN_PIE_las_filas_entran(tarea):
    """The reason V2-320 exists: a request resolved only by search cannot leave the sheet empty."""
    _sembrar([])
    assert F.hand_search_rows(_Rec(), MEDIDO) > 0
    assert (SHEET.view_data("v376-hoja") or {}).get("items")


def test_una_vuelta_SIN_titulos_no_entra():
    _sembrar([])
    assert F.hand_search_rows(_Rec(), {"results": [{"title": "", "url": "u"}]}) == 0


# ── and the turn reads it for what it is ───────────────────────────────────────────────────────────────────

def test_la_cara_NO_la_llama_candidato_sin_precio(tarea):
    _sembrar([{"title": "Descensos de Barranquismo en Vizcaya: 9 precios y ofertas 2026",
               "url": "https://x.invalid/a", "facts": [{"label": "Origen", "value": "búsqueda web"}]}])
    (fila,) = LB._sheet_top_rows(tarea, 5)
    assert "SIN PRECIO" not in fila
    assert "PÁGINA WEB por mirar" in fila and "aún no es un candidato" in fila


def test_una_ficha_CON_precio_no_cambia(tarea):
    """Sensitivity: the mark must not affect genuine listings."""
    _sembrar([{"title": "Tour en kayak por Bilbao", "price": "35 €", "url": "https://x.invalid/b"}])
    assert LB._sheet_top_rows(tarea, 5) == ["«Tour en kayak por Bilbao — 35 €»"]


def test_una_ficha_SIN_precio_y_SIN_marca_sigue_diciendo_SIN_PRECIO(tarea):
    """V2-360 intact: an insurer without an amount must still say that it does not include one."""
    _sembrar([{"title": "Allianz Direct", "url": "https://x.invalid/c"}])
    (fila,) = LB._sheet_top_rows(tarea, 5)
    assert "SIN PRECIO" in fila


# ── and, while we are at it, a branch that was DEAD ─────────────────────────────────────────────────────────

def test_el_TELEFONO_por_fin_llega_a_la_cara(tarea):
    """V2-360 read `item["tel"]`, and `intake._to_item` stores the phone number in `facts` as “Phone” — meaning
    that for ANY row passing through the shared doorway, that branch never ran and the plumber came out as
    “NO PRICE” despite having his number inside. Verified before stating it: the sheet does not preserve any
    `tel` key."""
    _sembrar([{"title": "Fontaneros 24H Bilbao",
               "facts": [{"label": "Teléfono", "value": "944123456"}], "url": "https://x.invalid/d"}])
    it = ((SHEET.view_data("v376-hoja") or {}).get("items") or [{}])[0]
    assert it.get("tel") is None, "premisa: la hoja no guarda una clave `tel`"
    (fila,) = LB._sheet_top_rows(tarea, 5)
    assert "944123456" in fila


def test_el_TELEFONO_gana_a_la_marca_de_pista(tarea):
    """A number to call is actionable (V2-240); its provenance does not make it otherwise."""
    _sembrar([{"title": "Escuela de surf Sopelana", "url": "https://x.invalid/e",
               "facts": [{"label": "Teléfono", "value": "944999888"},
                         {"label": "Origen", "value": "búsqueda web"}]}])
    (fila,) = LB._sheet_top_rows(tarea, 5)
    assert "944999888" in fila and "PÁGINA WEB" not in fila


def test_la_puerta_conserva_el_telefono_Y_la_marca():
    """`_to_item` built `facts` from scratch with the phone number, so any `facts` arriving in the row
    were lost entirely."""
    it = IN._to_item({"title": "Cosa", "tel": "600111222",
                      "facts": [{"label": "Origen", "value": "búsqueda web"}]})
    etiquetas = [f["label"] for f in it["facts"]]
    assert "Teléfono" in etiquetas and "Origen" in etiquetas
