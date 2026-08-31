"""When NO row in the sheet fits, the face says so — it does not deliver the one that fits least poorly (V2-318).

The heading of the «HAS ALREADY FOUND» block said «TELL IT: WHAT you found, with name and price», and the row
block, four lines below, said «only say what RESPONDS to what they asked for». Two conflicting orders within
the same block, and the first one wins: it is imperative and comes first.

Measured in guitar round 37 (2026-08-25 15:51), turn 10. With THREE rows in the sheet and none valid
for a request for «a second-hand acoustic under €150», it recited all three in raw order:

    «ya hay candidatos: "Guitarra Clásica Acústica — 200 €"; "Colgador de Guitarra Punk - Base Madera — 5 €";
     "Guitarra Acústica Taylor CE114 — 700 €". Dime si alguno te encaja»

A guitar HANGER offered as a candidate to someone who wants a guitar. And six turns later, with the
sheet full, it filtered flawlessly: «I discard those that are not guitars —case, CD, luthier— and the one at €350».
So it knows how to filter. What it did not know was what to say when the filter removes EVERYTHING, and then the reflex is
to deliver what is there — because staying silent looks like failure.

The branch goes INSIDE the imperative (operator rule: one instruction per block; two orders in one sentence are
decided by a coin toss). This test fixes the fact that both halves travel together.
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


def _face(goal: str, sheet: str, items: list[dict]) -> str:
    tid = T.create(goal, sheet=sheet)
    T.set_status(tid, "working")
    SHEET.apply_action("present", {"sheet": sheet, "title": "Resultados", "items": items})
    return "\n".join(LB.navegador_lines())


def test_el_imperativo_PIDE_lo_que_encaja_no_lo_que_hay():
    state = _face("Busca una guitarra acústica por debajo de 150 €", "v318-1",
                  [{"title": "Guitarra Acústica Fender CD-60", "price": "120 €"}])
    assert "CUÉNTALE en este turno LO QUE ENCAJE" in state


def test_y_LLEVA_la_rama_de_que_no_encaje_ninguna():
    """The missing half. Without it, the model has an instruction to count and no correct way not to
    count, so it counts — exactly what it did in turn 10 of round 37."""
    state = _face("Busca una guitarra acústica por debajo de 150 €", "v318-2",
                  [{"title": "Guitarra Clásica Acústica", "price": "200 €"},
                   {"title": "Colgador de Guitarra Punk - Base Madera", "price": "5 €"},
                   {"title": "Guitarra Acústica Taylor CE114", "price": "700 €"}])
    assert "NINGUNA" in state
    assert "ninguna cumple lo que pidió" in state


def test_la_alternativa_es_SEGUIR_no_callarse():
    """Saying «there is nothing» and stopping there is the other way to lose the operator: the branch must also say that
    the search continues, or the turn sounds like surrender."""
    state = _face("Busca una guitarra acústica por debajo de 150 €", "v318-3",
                  [{"title": "Colgador de Guitarra", "price": "5 €"}])
    low = state.lower()
    assert "sigues" in low or "sigue" in low
    assert "en vez de ofrecerle la que menos desencaja" in state


def test_las_filas_SIGUEN_viajando_la_rama_no_las_sustituye():
    """The risk of the fix: that adding «say that none fit» would stop sending the content, and the
    model would have to decide whether anything fits without seeing the lines. It is the V2-298 failure in reverse."""
    state = _face("Busca una guitarra acústica por debajo de 150 €", "v318-4",
                  [{"title": "Guitarra Acústica Taylor CE114", "price": "700 €"}])
    assert "LO QUE YA HA ENTREGADO" in state
    assert "Guitarra Acústica Taylor CE114 — 700 €" in state


def test_y_la_regla_de_JUICIO_sigue_puesta():
    """The other half of V2-298: the sheet keeps everything the page provided, and judging belongs to the turn."""
    state = _face("Busca una guitarra acústica por debajo de 150 €", "v318-5",
                  [{"title": "Estuche Guitarra", "price": "20 €"}])
    assert "la hoja guarda TODO lo que dio la página" in state
    assert "no un accesorio" in state
