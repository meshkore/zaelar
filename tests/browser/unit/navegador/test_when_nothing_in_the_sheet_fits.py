"""Cuando NINGUNA fila de la hoja encaja, la cara dice eso — no entrega la que menos desencaja (V2-318).

La cabeza del bloque «YA HA ENCONTRADO» decía «CUÉNTASELO: QUÉ ha encontrado, con nombre y precio» y el bloque
de filas, cuatro líneas más abajo, decía «di solo lo que RESPONDE a lo que pidió». Dos órdenes en tensión dentro
del mismo bloque, y gana la primera: es imperativa y viene antes.

Medido en la ronda 37 de la guitarra (2026-08-25 15:51), turno 10. Con TRES filas en la hoja y ninguna válida
contra un encargo de «acústica de segunda mano por debajo de 150 €», recitó las tres en orden crudo:

    «ya hay candidatos: "Guitarra Clásica Acústica — 200 €"; "Colgador de Guitarra Punk - Base Madera — 5 €";
     "Guitarra Acústica Taylor CE114 — 700 €". Dime si alguno te encaja»

Un COLGADOR de guitarra ofrecido como candidato a quien quiere una guitarra. Y seis turnos después, ya con la
hoja llena, filtró impecablemente: «las que no son guitarras —estuche, CD, luthier— y la de 350 € las descarto».
O sea que sabe filtrar. Lo que no sabía es qué decir cuando el filtro se lo lleva TODO, y ahí el reflejo es
entregar lo que hay — porque callarse se parece a fracasar.

La rama va DENTRO del imperativo (norma del operador: una instrucción por bloque; dos órdenes en una frase salen
a cara o cruz). Este test fija que las dos mitades viajan juntas.
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
    """La mitad que faltaba. Sin ella el modelo tiene una orden de contar y ninguna forma correcta de no
    contar, así que cuenta — que es exactamente lo que hizo el turno 10 de la ronda 37."""
    state = _face("Busca una guitarra acústica por debajo de 150 €", "v318-2",
                  [{"title": "Guitarra Clásica Acústica", "price": "200 €"},
                   {"title": "Colgador de Guitarra Punk - Base Madera", "price": "5 €"},
                   {"title": "Guitarra Acústica Taylor CE114", "price": "700 €"}])
    assert "NINGUNA" in state
    assert "ninguna cumple lo que pidió" in state


def test_la_alternativa_es_SEGUIR_no_callarse():
    """Decir «no hay nada» y punto es la otra forma de perder al operador: la rama tiene que decir también que
    la búsqueda sigue, o el turno suena a rendición."""
    state = _face("Busca una guitarra acústica por debajo de 150 €", "v318-3",
                  [{"title": "Colgador de Guitarra", "price": "5 €"}])
    low = state.lower()
    assert "sigues" in low or "sigue" in low
    assert "en vez de ofrecerle la que menos desencaja" in state


def test_las_filas_SIGUEN_viajando_la_rama_no_las_sustituye():
    """El riesgo del arreglo: que al añadir «di que no encaja ninguna» se dejara de mandar el contenido, y el
    modelo tuviera que decidir el encaje sin ver las líneas. Es la avería de V2-298 al revés."""
    state = _face("Busca una guitarra acústica por debajo de 150 €", "v318-4",
                  [{"title": "Guitarra Acústica Taylor CE114", "price": "700 €"}])
    assert "LO QUE YA HA ENTREGADO" in state
    assert "Guitarra Acústica Taylor CE114 — 700 €" in state


def test_y_la_regla_de_JUICIO_sigue_puesta():
    """La otra mitad de V2-298: la hoja guarda todo lo que dio la página, y juzgar es del turno."""
    state = _face("Busca una guitarra acústica por debajo de 150 €", "v318-5",
                  [{"title": "Estuche Guitarra", "price": "20 €"}])
    assert "la hoja guarda TODO lo que dio la página" in state
    assert "no un accesorio" in state
