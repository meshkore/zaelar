"""A travel row that states a route must join the two places he asked for (node 2.650).

find-direct-flight-budget ES (2026-10-14): a direct Madrid–Rome ask ended with a sheet of four other routes —
«Buscar vuelos de Logroño (RJL) a Madrid (MAD) desde 88 €», «de Madrid (MAD) a Lisboa (LIS)…» — the navigation
links of a fare page. `search.route_fit` reads the route from his words or the sheet's own title and criteria,
matches places by name or code in ES/EN, and leaves alone every row that states no route.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from search import route_fit

FIX = Path(__file__).resolve().parents[1] / "fixtures"
CTX_ES = ["Vuelos Madrid-Roma fin de semana 13 nov 2026", "Madrid (MAD) a Roma (FCO o CIA)", "Vuelos directos, sin escalas"]


def _fixture(name: str) -> dict:
    return json.loads((FIX / "routes" / f"{name}.json").read_text(encoding="utf-8"))


def test_every_recorded_off_route_link_is_judged_off():
    d = _fixture("find-direct-flight-budget__es__results--4abde9-1-offroute")
    route = route_fit.asked_route("", [d["title"]])
    assert route["names"] == ("Madrid", "Roma")
    for row in d["extracted"]:
        assert route_fit.why_off(row, route), row["title"]


def test_the_rows_the_card_clipped_are_judged_by_the_origin_they_still_show():
    d = _fixture("find-direct-flight-budget__es__results--4abde9-1-offroute")
    route = route_fit.asked_route("", [d["title"]])
    verdicts = {r["title"]: route_fit.why_off(r, route) for r in d["items"]}
    assert verdicts["Buscar vuelos de Logroño (RJL) a…"] and verdicts["Buscar vuelos de Barcelona (BCN)…"]
    assert verdicts["Buscar vuelos de Palma (PMI) a…"]
    assert verdicts["Buscar vuelos de Madrid (MAD) a…"] == ""     # its destination was cut: nothing contradicts


@pytest.mark.parametrize("name", ["find-direct-flight-budget__es__results--4abde9-1",
                                  "find-direct-flight-budget__en__results--dd5ff2-1"])
def test_no_row_of_the_recorded_right_sheets_is_judged_off(name):
    d = _fixture(name)
    crit = d.get("criteria") or {}
    on, off = route_fit.split(d["items"], [], "", [d["title"]] + list(crit.get("hard") or []))
    assert not off, off


def test_rome_roma_and_its_airports_are_one_place_and_the_return_leg_is_the_same_trip():
    route = route_fit.asked_route("NYC to Rome, nonstop", [])
    for title in ("JFK → FCO", "Rome → New York", "Vuelo Nueva York – Roma", "Newark to Rome", "Roma (FCO) → NYC"):
        assert route_fit.why_off({"title": title}, route) == "", title
    assert "Milan" in route_fit.why_off({"title": "New York to Milan"}, route)


def test_his_own_words_win_over_the_sheet_title():
    route = route_fit.asked_route("No, mejor Madrid a Lisboa", CTX_ES)
    assert route["names"] == ("Madrid", "Lisboa")


def test_a_row_that_states_no_route_or_one_place_is_left_alone():
    route = route_fit.asked_route("", CTX_ES)
    for title in ("Ryanair 110 EUR", "Opcion 122 EUR — Ida el 13 nov a las 08:55 desde MAD",
                  "Sale de Aeropuerto Adolfo Suárez Madrid-Barajas", "Vuelos MAD→FCO/CIA"):
        assert route_fit.why_off({"title": title}, route) == "", title


def test_an_unknown_place_is_judged_only_in_the_explicit_de_a_form():
    route = route_fit.asked_route("", CTX_ES)
    assert route_fit.why_off({"title": "Madrid-Torrejón shuttle"}, route) == ""
    assert route_fit.why_off({"title": "Vuelos de Logroño a Roma"}, route)


def test_a_request_that_is_not_about_travel_asks_no_route():
    assert route_fit.asked_route("Hoteles en Madrid - Centro", ["Hoteles Madrid - Centro"]) == {}


@pytest.mark.parametrize("path", sorted((FIX / "sheets").glob("*.json")), ids=lambda p: p.stem)
def test_no_row_of_any_other_recorded_sheet_is_judged_off(path):
    d = json.loads(path.read_text(encoding="utf-8"))
    crit = d.get("criteria") or {}
    ctx = [d.get("title"), crit.get("goal")] + list(crit.get("changes") or []) + list(crit.get("hard") or [])
    on, off = route_fit.split(d.get("items") or [], [], str(d.get("asked") or ""), [c for c in ctx if c])
    assert not off, off
