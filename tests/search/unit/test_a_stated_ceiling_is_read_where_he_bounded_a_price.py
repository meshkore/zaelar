"""A price ceiling is read only where he BOUNDED a price, and the last one he said wins (node 2.668).

search-buy-laptop ES (2026-10-14): «por menos de 1.800 euros» — the sheet's door never read it as a ceiling. A
bound needs a currency next to the number, or a bare number of at least 100 that no noun follows: «menos de
50.000 km», «hasta 27 pulgadas», «over 100 reviews» are quantities, not prices.
"""
from __future__ import annotations

import pytest

from search import ceiling_fit


@pytest.mark.parametrize("text,value,currency,unit", [
    ("Búscame un MacBook Pro M5 por menos de 1.800 euros, nuevo o reacondicionado.", 1800, "EUR", ""),
    ("Find me an apartment to rent in Austin, two bedrooms, under $1,900 a month, pets allowed.", 1900, "USD", "month"),
    ("Find me a used car, diesel or hybrid, under 60k miles and under $14,000", 14000, "USD", ""),
    ("un coche que no pase de 12 mil euros", 12000, "EUR", ""),
    ("algo entre 1.500 y 1.800 €", 1800, "EUR", ""),
    ("a hotel under $300 a night", 300, "USD", "night"),
    ("no more than 2,500 dollars", 2500, "USD", ""),
    ("max 500€", 500, "EUR", ""),
    ("Busco un piso en Madrid, hasta 1.200 al mes", 1200, "", "month"),
    ("Perdona, pero esos están por encima de 1.800, no me sirven.", 1800, "", ""),
])
def test_a_bounded_price_is_his_ceiling(text, value, currency, unit):
    got = ceiling_fit.asked_ceiling(text)
    assert got == {"value": value, "currency": currency, "unit": unit}, text


@pytest.mark.parametrize("text", [
    "menos de 50.000 km", "un monitor de hasta 27 pulgadas", "hasta 27", "hasta 1080p", "up to 2000 rpm",
    "over 100 reviews, no good", "hotel under 15 days", "¿hay alguno por encima de 2.000?", "el de 1.663 € me gusta",
])
def test_a_quantity_or_a_price_he_only_mentioned_is_no_ceiling(text):
    assert ceiling_fit.asked_ceiling(text) is None, text


def test_the_last_ceiling_he_said_wins_and_his_words_beat_the_sheet():
    ask = "Búscame un portátil por menos de 1.000 €. Vale, mejor hasta 1.400 €"
    assert ceiling_fit.asked_ceiling(ask)["value"] == 1400
    assert ceiling_fit.asked_ceiling(ask, ["Portátiles hasta 900 €"])["value"] == 1400
    assert ceiling_fit.asked_ceiling("busco un portátil", ["Portátiles hasta 900 €"])["value"] == 900


def test_a_distance_in_km_is_never_a_thousands_price():
    """search-buy-camper ES (2026-10-14): «menos de 150.000 km, por debajo de 25.000 euros» read the «k» of «km»
    as «mil» and set a 150,000,000 ceiling — 73 real campers were judged against it."""
    from search import asked
    assert asked.ceiling("Busco una camper con menos de 150.000 km, por debajo de 25.000 euros") == 25000.0
    assert asked.ceiling("hasta 15k €") == 15000.0
