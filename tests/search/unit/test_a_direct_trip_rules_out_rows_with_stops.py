"""A direct trip he asked for rules out a row that states stops (node 2.651).

find-direct-flight-budget ES/EN (2026-10-14): «directo eh, que no me apetece nada hacer escala» / «nonstop though, I
really can't deal with layovers». The sheet's hard criteria said «Vuelos directos, sin escalas»; no gate read it.
"""
from __future__ import annotations

from search import route_fit

CTX = ["Vuelos Madrid-Roma", "Vuelos directos, sin escalas"]


def test_a_row_with_stops_is_off_when_direct_was_asked():
    route = route_fit.asked_route("", CTX)
    assert route["direct"] is True
    for title in ("Iberia MAD → FCO 1 escala", "Madrid → Roma, con escala en Barcelona", "Madrid to Rome · 2 stops"):
        assert "direct" in route_fit.why_off({"title": title}, route), title


def test_a_direct_row_or_one_that_says_nothing_of_stops_stays():
    route = route_fit.asked_route("", CTX)
    for title in ("Madrid → Roma, directo", "Madrid → Roma · 0 escalas", "Madrid → Roma sin escalas", "Ryanair 110 EUR"):
        assert route_fit.why_off({"title": title}, route) == "", title


def test_stops_are_not_judged_when_he_did_not_ask_for_direct():
    route = route_fit.asked_route("vuelos Madrid–Roma, lo más barato", [])
    assert route["direct"] is False
    assert route_fit.why_off({"title": "Madrid → Roma 1 escala"}, route) == ""


def test_the_english_ask_reads_nonstop():
    route = route_fit.asked_route("flights NYC to Rome, nonstop though", [])
    assert route["direct"] is True
    assert route_fit.why_off({"title": "Newark to Rome, 1 stop"}, route)
