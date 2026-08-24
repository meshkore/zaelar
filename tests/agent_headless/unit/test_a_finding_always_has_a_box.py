"""V2-290 — el navegador extraía filas reales y caían en la caja que no es de nadie.

Medido en la tanda del 2026-08-24 12:03. `search-buy-bicycle__es`: el navegador navegó 6 veces, extrajo 3 veces
y sacó SIETE bicis con precio y enlace de Wallapop —«Bicicleta Montaña Venta en Persona, 125 €», «Rock Shox
Trutativ, 70 €»…— y las siete se escribieron en `results` PELADO, mientras `results::3fc631-1` —la hoja del
encargo, abierta y con su título— se quedaba en cero. Lo mismo en `search-buy-camera__es`, con catorce. Y la
caja pelada **no es de nadie desde V2-259**, así que aquello era invisible por construcción: el operador con una
tarjeta en blanco delante y los resultados en una caja que nadie le abrió.

DOS grietas encadenadas, y arreglar una sola deja el fallo entero en pie:

  1. **La pestaña no se llama siempre igual.** `dispatch._prepare_web` crea la pestaña y guarda `rec.nav_task`
     SOLO para `kind="web"`. Cualquier otro encargo que abra el navegador —el de INVESTIGACIÓN de la bici, sin
     ir más lejos— cae al fallback de `nucleo/nav_cli.py` (`ZAELAR_NAV_TASK` o, si no, `ZAELAR_TASK_ID`), así
     que su pestaña se llama como la TAREA. `sheet_for_nav_task` solo casaba por `nav_task`, y esa vuelta no
     existía. Dos formas de nombrar lo mismo en dos sitios distintos es como nació la grieta.

  2. **Y ese encargo puede no tener hoja.** Se abre al encargar solo si el cerebro declaró la hoja como
     superficie, lo cual es correcto: no se le abre una caja vacía a quien no va a llenarla. Pero si acaba
     extrayendo filas, la premisa se cae — hay hallazgos y no hay dónde ponerlos. Se abre al llegar el PRIMERO,
     que es la diferencia entre una caja vacía que nadie pidió y una que aparece con algo dentro.
"""
import pytest

from nucleo import dispatch, sheets


class _Rec:
    """Lo mínimo que las dos funciones miran de un record."""
    def __init__(self, task_id, *, nav_task="", sheet="", status="running"):
        self.task_id, self.nav_task, self.sheet, self.status = task_id, nav_task, sheet, status
        self.goal, self.kind, self.surface = "busca una bici", "research", ""


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    yield


# ── 1) la RESOLUCIÓN, pura ────────────────────────────────────────────────────────────────────────────────
def test_a_reserved_tab_still_resolves_by_its_nav_task():
    """La vuelta que ya existía sigue mandando: se pregunta primero por la pestaña reservada."""
    recs = [_Rec("1", nav_task="t1", sheet="b-1")]
    assert sheets.sheet_for_nav_task("t1", recs) == "b-1"


def test_a_tab_named_after_its_errand_resolves_too():
    """EL CASO MEDIDO: sin pestaña reservada, el puente la llama por el id de la TAREA."""
    recs = [_Rec("3", sheet="b-3")]
    assert sheets.sheet_for_nav_task("3", recs) == "b-3"


def test_the_nav_task_wins_when_both_could_match():
    """Un id de tarea puede coincidir con la pestaña de OTRO encargo; la reserva explícita es la más específica
    y tiene que ganar, o un hallazgo acabaría en la hoja del vecino."""
    recs = [_Rec("9", sheet="b-suyo"), _Rec("1", nav_task="9", sheet="b-reservada")]
    assert sheets.sheet_for_nav_task("9", recs) == "b-reservada"


def test_a_tab_with_no_errand_behind_it_still_answers_nothing():
    """El operador conduciendo el navegador a mano no tiene encargo, y eso NO es un fallo: devuelve "" y se
    escribe la hoja de siempre (contrato de V2-259)."""
    assert sheets.sheet_for_nav_task("t9", [_Rec("1", nav_task="t1", sheet="b-1")]) == ""
    assert sheets.sheet_for_nav_task("", [_Rec("1", nav_task="t1", sheet="b-1")]) == ""


# ── 2) y la APERTURA a demanda, que es la que necesita el registro vivo ───────────────────────────────────
def _opened(monkeypatch):
    """Sella la hoja como lo haría `_sheet_open`, sin tocar el almacén de widgets.

    ⚠️ Se parchea en `nucleo.sheets`, que es DONDE SE USA, no en `dispatch`, que solo lo re-exporta por nombre:
    reapuntar el nombre de `dispatch` deja al llamante real llamando al de verdad. Costó un rojo al mover el
    cuerpo de una función entre módulos, y es la misma trampa que hace peligroso extraer cualquier cosa que un
    test parchee por su nombre privado."""
    seen = []

    def _fake(rec):
        seen.append(rec)
        rec.sheet = f"hoja-{rec.task_id}"
    monkeypatch.setattr(sheets, "_sheet_open", _fake)
    return seen


def test_the_first_finding_opens_the_box_its_errand_never_had(monkeypatch):
    """EL CASO MEDIDO ENTERO: encargo vivo, sin hoja, y una pestaña que acaba de extraer."""
    seen = _opened(monkeypatch)
    dispatch._SESSIONS["3"] = _Rec("3")                    # sin `sheet`: su superficie no era la hoja
    assert dispatch.sheet_for_nav_task("3") == "hoja-3"
    assert len(seen) == 1


def test_an_errand_that_already_has_a_box_is_not_opened_again(monkeypatch):
    """Estrenarla otra vez es el «error de borrar búsquedas» que V2-259 vino a quitar."""
    seen = _opened(monkeypatch)
    dispatch._SESSIONS["3"] = _Rec("3", sheet="b-3")
    assert dispatch.sheet_for_nav_task("3") == "b-3"
    assert seen == []


def test_a_finding_from_a_dead_errand_opens_nothing(monkeypatch):
    """Un hallazgo que llega tarde no estrena una tarjeta en la pantalla de alguien que ya pasó a otra cosa."""
    seen = _opened(monkeypatch)
    dispatch._SESSIONS["3"] = _Rec("3", status="done")
    assert dispatch.sheet_for_nav_task("3") == ""
    assert seen == []


def test_nothing_is_opened_for_a_tab_nobody_owns(monkeypatch):
    """El navegador a mano sigue escribiendo en la hoja de siempre, sin estrenar cajas por el camino."""
    seen = _opened(monkeypatch)
    dispatch._SESSIONS["3"] = _Rec("3", sheet="b-3")
    assert dispatch.sheet_for_nav_task("t9") == ""
    assert seen == []
