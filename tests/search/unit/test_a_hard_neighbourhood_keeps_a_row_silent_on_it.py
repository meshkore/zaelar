"""A hard «solo en Ruzafa» stays a PLACE, never a subject: a row that does not mention the neighbourhood is kept,
and the city gate still judges the city (node 2.676).

Neighbourhood names are not in `place_words`: absence of place information keeps the row (search-rent-apartment
ES, 2026-10-14).
"""
from __future__ import annotations

from search import category, place_fit, row_fit

FC = "https://www.fotocasa.es/es/alquiler/vivienda/"
ASK = "Búscame un piso de alquiler en Valencia, solo en Ruzafa, por menos de 1.100 euros"


def test_a_hard_neighbourhood_is_no_subject():
    assert category.asked_from(ASK)["subjects"] == []


def test_a_row_silent_on_the_neighbourhood_stays_and_another_city_still_leaves():
    rows = [
        {"title": "Piso con 2 baños", "price": "1.045 €", "url": FC + "valencia-capital/ascensor/189303858/d"},
        {"title": "Ático luminoso", "price": "990 €"},
        {"title": "Piso en Torrent", "subtitle": "Torrent", "price": "800 €"},
    ]
    on, off = row_fit.split(rows, ASK, [])
    assert [r["title"] for r in on] == ["Piso con 2 baños", "Ático luminoso"]
    assert [o["title"] for o in off] == ["Piso en Torrent"]
    assert "Torrent" in off[0]["why"]


def test_the_neighbourhood_is_not_the_asked_place():
    assert place_fit.asked_place(ASK)["said"] == "Valencia"
