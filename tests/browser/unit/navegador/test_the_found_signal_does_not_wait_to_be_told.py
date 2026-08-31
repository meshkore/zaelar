"""The «found something» signal was a VOLUNTARY REPORT, and the worker does not always make it (V2-284).

Measured in the 2026-08-24 03:02 batch, reading the prompts from the TEN turns of
`search-secondhand-monitor__es`: the face did not appear even once. The browser line said

    «Busca en marketplaces de segunda mano (Wallapop, etc.) un monitor de a» — en es.wallapop.com, 1 pasos dados

and nothing else, in all ten, while the mechanism from that same round recorded **11 navigations, 5
extractions** and real monitors with a price and link (MSI MAG 70 €, Dell P2714H 60 €, BenQ 60 €). The same
silence in THREE of the four cases in the batch, and the verdict in all three was the same: «it had real
results from the worker and did not deliver them». The judge was right about the fact and wrong about the
culprit: the turn's prompt never received any indication that there was something.

The cause: `_found_candidates` read ONLY `rec.kept`, which exists if the worker remembered to call
`hbnote considered --kept N`. A report that someone has to remember to make is not a signal, it is a courtesy.

The sheet rows are a fact that does not depend on anyone remembering: `intake.push` writes them when the
browser extracts (V2-257). And they are read by the TAB, not from the live-session registry, because the
moment this is most needed is precisely when the worker is no longer there (V2-281).
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
    """Regression check: with the sheet empty, the face remains silent, as it should."""
    tid = T.create("Busca un monitor de segunda mano", sheet="v284-vacia")
    assert LB._found_candidates(tid) is False


def test_una_fila_SIN_nombre_no_es_un_resultado():
    """Same rule as the browser note (V2-234): a link that was on the page is not a finding.

    ⚠️ And the thing that actually enforces it is THE SHEET, not this predicate: `apply_action` discards the
    untitled row on entry — measured below. So the `_sheet_has_rows` filter is currently a belt over suspenders,
    and this is stated because a test that claims to cover something already guaranteed by the adjacent layer
    LIES about its coverage (the teardown showed it: removing the filter did not make anything fail).
    """
    tid = T.create("Busca un monitor", sheet="v284-2")
    SHEET.apply_action("present", {"sheet": "v284-2", "title": "Resultados",
                                   "items": [{"title": "", "url": "https://x.example/categoria"}]})
    assert (SHEET.view_data("v284-2") or {}).get("items") == [], (
        "la hoja dejó de descartar la fila sin nombre: ahora el filtro de `_sheet_has_rows` SÍ es el mecanismo")
    assert LB._found_candidates(tid) is False


def test_una_pestana_SIN_encargo_detras_no_mira_ninguna_hoja():
    """The operator driving the browser manually: without a stamp, there is no task sheet to consult.

    The BARE box is deliberately filled in this case, which is what makes it bite: without the guard,
    `view_data("")` reads it and the face would trigger on leftovers from ANOTHER round — 38 accumulated rows
    measured in the 2026-08-24 batch. A ghost shaped like a finding.
    """
    SHEET.apply_action("present", {"sheet": "", "title": "Resultados",
                                   "items": [{"title": "Guitarra de otra ronda", "price": "100 €"}]})
    assert (SHEET.view_data("") or {}).get("items"), "la caja de nadie tiene que estar llena para que muerda"
    assert LB._found_candidates(T.create("el operador abre una web")) is False


def test_el_reporte_del_worker_SIGUE_valiendo():
    """One signal is not substituted for another: `kept` arrives before the sheet when the worker does report."""
    from nucleo import dispatch as D
    from nucleo.workers.session import SessionRecord
    tid = T.create("Busca un monitor", sheet="v284-3")
    rec = SessionRecord(task_id="w1", goal="Busca un monitor", kind="web")
    rec.nav_task, rec.kept, rec.status = tid, 4, "running"
    D._SESSIONS.clear()
    D._SESSIONS["w1"] = rec
    try:
        assert LB._found_candidates(tid) is True      # with the sheet still empty
    finally:
        D._SESSIONS.clear()


def test_y_la_cara_LLEGA_al_estado_cuando_la_hoja_tiene_filas():
    """The wiring half: the fact must appear in the block the turn reads, not only in the predicate.

    A fix whose predicate is correct but whose block does not show it passes its tests and changes nothing (V2-199).
    """
    tid = T.create("Busca un monitor de segunda mano", sheet="v284-4")
    T.set_status(tid, "working")
    _sheet_with("v284-4", ["Monitor Dell 27 P2714H LED"])
    state = "\n".join(LB.navegador_lines())
    assert "YA HA ENCONTRADO ALGO" in state
    # V2-330: without written rows, the instruction is to tell the truth about what exists, not recite what it lacks.
    # V2-443 — the NO-ROWS branch changed its text (it now marks the count as coming from the worker), so the
    # alternative is updated: leaving it pointing to a phrase that no longer exists makes it unreachable, and the
    # `or` would end up checking only one thing without anything failing.
    assert ("CUÉNTALE en este turno LO QUE ENCAJE" in state
            or "DICE QUE YA TIENE CANDIDATOS" in state)
