"""The request itself says how many and which data fields (V2-782 T4.4 / T3.2), in both languages.

Measured 2026-10-10: «pull a couple of recipes» became a brief with 40 candidates (round two: 80), ~90 gathered,
265 s, and the answer arrived after the conversation. The number he said is his.
"""
from __future__ import annotations

import pytest

from search import criteria


@pytest.mark.parametrize("phrase,n", [
    ("sácame un par de recetas sin gluten", 3), ("pull a couple of gluten-free recipes", 3),
    ("dame las tres mejores pizzerías", 3), ("give me the three best pizzerias", 3),
    ("ponme veinte coches", 20), ("show me twenty cars", 20),
    ("quiero 5 hoteles en Soria", 5), ("I want 5 hotels in Soria", 5),
    ("uno bueno nada más", 1), ("just one good one", 1), ("el mejor valorado", 1), ("the best one", 1),
    ("unas pocas ideas", 3), ("a few ideas", 3), ("algunas opciones", 5), ("some options", 5),
])
def test_the_number_he_said_is_his(phrase, n):
    b = criteria.breadth(phrase)
    assert b["n_final"] == n, (phrase, b)
    assert b["said"]
    assert 6 <= b["min_candidates"] <= 25


@pytest.mark.parametrize("phrase", ["busca un piso en alquiler", "find a flat to rent", "busca campers de segunda mano",
                                    "find second-hand campers", "una bici de montaña", "a mountain bike"])
def test_an_article_is_not_a_number(phrase):
    """«un piso» / «a flat» is a flat, not ONE flat: the default breadth stands."""
    b = criteria.breadth(phrase)
    assert b == {"n_final": 10, "min_candidates": 25, "said": ""}, (phrase, b)


def test_a_said_number_lowers_the_floor_but_never_raises_it():
    assert criteria.breadth("dame dos hoteles")["min_candidates"] == 8
    assert criteria.breadth("ponme veinte hoteles")["min_candidates"] == 25
    assert criteria.breadth("ponme 30 hoteles")["n_final"] == 30 and criteria.breadth("ponme 30 hoteles")["min_candidates"] == 25


@pytest.mark.parametrize("phrase,fields", [
    ("el fontanero mejor valorado que pueda venir hoy", ["rating", "availability"]),
    ("the best-rated plumber who can come today", ["rating", "availability"]),
    ("un monitor 4K de 27 pulgadas barato", ["price"]), ("a cheap 27-inch 4K monitor", ["price"]),
    ("hotel por menos de 150 € con buenas opiniones", ["price", "rating"]),
    ("hotel under $150 with good reviews", ["price", "rating"]),
    ("un barbero con hueco este fin de semana", ["availability"]), ("a barber available this weekend", ["availability"]),
    ("fotos del Ferrari Amalfi", []), ("pictures of the Ferrari Amalfi", []),
])
def test_the_fields_he_asked_for(phrase, fields):
    assert criteria.fields(phrase) == fields, phrase
    assert len(criteria.hard_criteria(phrase)) == len(fields)


def test_for_request_bundles_everything():
    out = criteria.for_request("dame tres hoteles baratos")
    assert out["n_final"] == 3 and out["fields"] == ["price"] and out["hard"] == ["price"]
