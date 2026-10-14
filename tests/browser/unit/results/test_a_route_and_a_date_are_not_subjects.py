"""A route's places and a date abbreviation are not the subject a row must name (node 2.653).

find-direct-flight-budget EN (2026-10-14, sandbox 020044-en): the turn told him «about €653… for the nonstop Nov 6
to Nov 8 weekend» — a real row then («653 euros — €653», Google Flights). His «ok those dates work» was injected as
«…dates Nov 6-8 are good. Focus on the €653 nonstop option (NYC-Rome)…», the correction re-judged the sheet, read
«nov» and «rome» as SUBJECTS, and moved all twelve fare rows to the Rejected tab; the next present showed 703 € for
the same dates. The amount guard had nothing to catch: the figure was a row's price when it was said.
"""
from __future__ import annotations

from search import category
from widgets.results import category_gate, data as sheet

INJECTED = ("The operator confirms the dates Nov 6-8 are good. Focus on the €653 nonstop option (NYC-Rome) and report "
            "its departure/arrival times and airline — he wants well-timed flights, not crazy hours.")
ROWS = [{"title": "Leaves John F. Kennedy International Airport at 5:20 PM on Friday, November 6", "price": "€653"},
        {"title": "653 euros", "price": "€653"}, {"title": "Leaves Newark Liberty…", "price": "€988"}]


def test_the_injected_route_and_dates_ask_no_subject():
    assert category.asked_from(INJECTED)["subjects"] == []
    assert category.asked_from("vuelos Madrid–Roma, directo")["subjects"] == []


def test_a_proper_name_is_still_a_subject():
    assert category.asked_from("entradas para un concierto de Rosalía en Madrid")["subjects"] == ["rosalia"]


def test_the_correction_no_longer_empties_the_fare_rows():
    sheet.store.save(sheet.sheet_key("t2653"), {"title": "Buscar vuelos nonstop Nueva York–Roma", "items": list(ROWS)})
    assert category_gate.recheck("t2653", INJECTED) == 0
    assert [i["price"] for i in sheet.view_data("t2653")["items"]] == ["€653", "€653", "€988"]
