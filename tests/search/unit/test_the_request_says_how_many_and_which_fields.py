"""The request itself says how many and which data fields (V2-782 T4.4 / T3.2), in both languages.

Measured 2026-10-10: «pull a couple of recipes» became a brief with 40 candidates (round two: 80), ~90 gathered,
265 s, and the answer arrived after the conversation. The number he said is his; none said is undeclared (V2-840).
"""
from __future__ import annotations

import pytest

from search import criteria


@pytest.mark.parametrize("phrase,n", [
    ("dame las tres mejores pizzerías", 3), ("give me the three best pizzerias", 3),
    ("ponme veinte coches", 20), ("show me twenty cars", 20),
    ("quiero 5 hoteles en Soria", 5), ("I want 5 hotels in Soria", 5),
    ("ponme 30 hoteles", 30),
    ("uno bueno nada más", 1), ("just one good one", 1), ("el mejor valorado", 1), ("the best one", 1),
])
def test_the_number_he_said_is_his(phrase, n):
    b = criteria.breadth(phrase)
    assert b == {"n_final": n, "said": b["said"]} and b["said"], (phrase, b)


@pytest.mark.parametrize("phrase", ["busca un piso en alquiler", "find a flat to rent", "busca campers de segunda mano",
                                    "find second-hand campers", "una bici de montaña", "a mountain bike",
                                    # V2-840 H1: a vague quantity is his word, not a number of ours
                                    "sácame un par de recetas sin gluten", "pull a couple of gluten-free recipes",
                                    "unas pocas ideas", "a few ideas", "algunas opciones", "some options"])
def test_no_number_said_is_undeclared_never_a_default_of_ours(phrase):
    """«un piso» / «a flat» is a flat, not ONE flat; «a couple» is not three. Nothing said → undeclared: no floor, no
    default count, and nothing about how many to evaluate (the composing model decides, V2-840 H1)."""
    assert criteria.breadth(phrase) == {"n_final": None, "said": ""}, phrase


def test_the_grammar_holds_no_number_of_ours():
    import inspect
    assert list(inspect.signature(criteria.breadth).parameters) == ["request"]
    assert not hasattr(criteria, "_VAGUE")
    assert "min_candidates" not in criteria.breadth("dame dos hoteles")


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


@pytest.mark.parametrize("phrase,n", [
    ("can you find me like three 27 inch 4k monitors, under 400 bucks or so? show me when you've got them", 3),
    ("búscame tres monitores 4k de 27 pulgadas", 3), ("two 4k tvs", 2), ("dame dos 4k baratas", 2),
])
def test_a_measure_between_the_count_and_the_thing_is_not_the_count(phrase, n):
    """Demo 2026-10-22: «three 27 inch 4k monitors» read «27 inch» as the count — the errand became a top-ten
    over 25 candidates and ran 21 minutes until the budget killed it, with nothing delivered."""
    assert criteria.breadth(phrase)["n_final"] == n, (phrase, criteria.breadth(phrase))


def test_the_brief_is_the_composers_and_no_word_reader_overrides_it():
    """V2-840 H1: the composer reads his words («three monitors») and declares the count; a numeral reader beside it
    was a second, weaker opinion. `criteria.breadth` still serves the route; it is no source of the brief's target."""
    from nucleo.workers import brief as research
    raw = ('{"research": true, "goal": "monitors", "breadth": {"min_candidates": 12}, '
           '"deliverable": {"widget": "results", "n_final": 3}}')
    b = research.parse(raw, request="can you find me like ten 27 inch 4k monitors, under 400 bucks or so?")
    assert b["deliverable"]["n_final"] == 3 and b["breadth"]["min_candidates"] == 12