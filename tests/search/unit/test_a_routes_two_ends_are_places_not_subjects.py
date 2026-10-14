"""Both ends of a ROUTE in his words are places, never the subject every row must name (node 2.636).

His commissioning sentence now reaches every errand's sheet (node 2.630), so a trip's «de Madrid a Londres» would
otherwise ask every flight row to say «madrid» or «londres» — a row that says «MAD → LHR» or «London» would leave.
A place was already never a subject after «en/in/cerca de»; a route's origin and destination are the same fact.
"""
from __future__ import annotations

from search import asked, category


def test_a_route_names_no_subject_in_either_language():
    assert asked.subjects("Búscame un vuelo de Madrid a Londres el viernes, lo más barato") == []
    assert asked.subjects("find me a flight from Boston to Denver next Friday") == []
    assert asked.subjects("un tren desde Sevilla hasta San Sebastián") == []


def test_a_subject_beside_a_route_still_counts():
    assert asked.subjects("entradas para Rosalía, y el vuelo de Madrid a Barcelona") == ["rosalia"]


def test_a_flight_row_that_says_the_codes_stays():
    rows = [{"title": "Iberia IB3166 · MAD → LHR", "price": "120 €"}, {"title": "Vueling VY7820", "price": "89 €"}]
    assert len(category.split(rows, "Búscame un vuelo de Madrid a Londres el viernes", [])[0]) == 2
