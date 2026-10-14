"""A row that names only another city than the one asked is not a candidate; a row silent on place stays (node 2.672).

search-rent-apartment US (2026-10-14): «Azola Avery Centre» (…/Texas/Round-Rock-Apartments/…) and «Lively at
Gilbert» (…/Texas/Manor-Apartments/…) were offered as Austin apartments. And his «East Austin or downtown» made
«austin» a SUBJECT every row had to name, so a listing whose card named no city left the sheet: a known place is
never a subject.
"""
from __future__ import annotations

from search import category, place_fit, row_fit

ASK = ("Find me an apartment to rent in Austin, two bedrooms, under $1,900 a month, pets allowed. "
       "East Austin or downtown, with good transit")
AF = "https://www.apartmentfinder.com/Texas/"
ROWS = [
    {"title": "The Asher", "price": "$1,390", "url": AF + "Austin-Apartments/The-Asher-Apartments-k0nxg3c"},
    {"title": "Azola Avery Centre", "price": "$1,183", "url": AF + "Round-Rock-Apartments/Azola-Avery-Centre-x3vy91n"},
    {"title": "Lively at Gilbert", "price": "$1,129", "url": AF + "Manor-Apartments/Lively-At-Gilbert-bsvtn5b"},
    {"title": "1501 W Howard Ln Apt 5301", "subtitle": "Austin, TX 78753", "price": "$1,826"},
    {"title": "Hilltop Flats", "subtitle": "Pflugerville, TX 78660", "price": "$1,500"},
    {"title": "Bexley at Anderson Mill", "price": "$1,700"},
]


def test_the_measured_suburb_rows_leave_and_the_rest_stay():
    on, off = row_fit.split(ROWS, ASK, [])
    assert {o["title"] for o in off} == {"Azola Avery Centre", "Lively at Gilbert", "Hilltop Flats"}
    assert [r["title"] for r in on] == ["The Asher", "1501 W Howard Ln Apt 5301", "Bexley at Anderson Mill"]
    assert any("Round Rock, not Austin" in o["why"] for o in off)


def test_a_row_that_also_names_the_asked_city_stays():
    p = place_fit.asked_place("busco un coche en Madrid")
    assert not place_fit.why_off({"title": "SEAT Leon", "subtitle": "Familiar · Valdemoro (Madrid)"}, p)
    assert place_fit.why_off({"title": "SEAT Leon", "subtitle": "Familiar · Getafe"}, p)


def test_a_known_place_is_never_a_subject():
    assert category.asked_from(ASK)["subjects"] == []
    assert place_fit.not_places(["east austin", "madrid centro", "rosalia"]) == ["rosalia"]


def test_a_street_or_a_quarter_is_not_another_city():
    sf = place_fit.asked_place("an emergency plumber in San Francisco")
    assert not place_fit.why_off({"title": "Five Star", "facts": [{"label": "Address", "value": "811 San Jose Ave"}]}, sf)
    madrid = place_fit.asked_place("un fontanero en Madrid")
    assert not place_fit.why_off({"title": "Fontanería", "subtitle": "Avenida de Getafe 2"}, madrid)
    austin = place_fit.asked_place("an apartment in Austin")
    assert not place_fit.why_off({"title": "Loft", "subtitle": "Downtown Austin, TX"}, austin)
