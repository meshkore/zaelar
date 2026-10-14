"""The place a row is judged against is a KNOWN place his words name (node 2.671).

search-rent-apartment US (2026-10-14): «Find me an apartment to rent in Austin». The place is read from his words
(capitalised, or after «en / in / near»), else from the sheet's title and criteria; a suburb joins it only when he
widened the ask («y alrededores», «area», «near»); a trip is the route gate's, never this one's.
"""
from __future__ import annotations

from search import place_fit


def test_his_words_name_the_place_and_the_city_alone_is_accepted():
    p = place_fit.asked_place("Find me an apartment to rent in Austin, two bedrooms")
    assert p["names"] == {"austin"} and p["said"] == "Austin"
    assert place_fit.asked_place("busco piso en madrid")["names"] == {"madrid"}     # after «en», lowercase


def test_a_widened_ask_accepts_the_metro():
    p = place_fit.asked_place("", ["Coches diésel hasta 12.000 € · Madrid y alrededores"])
    assert {"madrid", "getafe", "valdemoro"} <= p["names"]
    assert "round rock" in place_fit.asked_place("an apartment in the Austin area")["names"]


def test_no_known_place_or_a_trip_asks_nothing_here():
    assert place_fit.asked_place("Búscame un MacBook Pro M5 en Amazon") == {}
    assert place_fit.asked_place("un vuelo directo de Madrid a Roma") == {}
    assert place_fit.asked_place("a manor house to rent") == {}                   # a word, not the town of Manor
