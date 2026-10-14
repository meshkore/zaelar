"""The sheet's door files the rows of another route as REJECTED, judging the row the worker SENT (node 2.652).

find-direct-flight-budget ES (2026-10-14): the browser's extraction pushed «Buscar vuelos de Logroño (RJL) a Madrid
(MAD) desde 88 €…» into a «Vuelos Madrid-Roma» sheet. The card clips a title at 34 characters BEFORE the category
gate runs, so the gate only ever saw «Buscar vuelos de Logroño (RJL) a…». The route gate reads the unclipped title
from the payload, files the row in the Rejected tab with its reason and tells the worker.
"""
from __future__ import annotations

from widgets.results import data as sheet

FULL = [
    {"title": "Buscar vuelos de Madrid (MAD) a Lisboa (LIS) desde 49 €. Operado por Ryanair. De 10 dic a", "price": "49 €"},
    {"title": "Buscar vuelos de Logroño (RJL) a Madrid (MAD) desde 88 €. Operado por Iberia.", "price": "88 €"},
    {"title": "Ryanair 110 EUR", "subtitle": "Ida 13 nov 21:55 MAD (FR9602) y vuelta 15 nov 06:25 FCO", "price": "110 EUR"},
]


def test_a_present_files_the_other_routes_with_their_reason():
    res = sheet.apply_action("present", {"sheet": "t2652a", "title": "Vuelos Madrid-Roma fin de semana", "items": FULL})
    view = sheet.view_data("t2652a")
    assert [i["title"] for i in view["items"]] == ["Ryanair 110 EUR"]
    whys = {r["title"]: r["why"] for r in view["rejected"]}
    assert len(whys) == 2 and all("Madrid – Roma" in w for w in whys.values())
    assert any("Lisboa" in w for w in whys.values())          # judged by the unclipped title
    assert "Rejected tab" in res.get("note_for_worker", "")


def test_an_append_meets_the_same_door():
    sheet.store.save(sheet.sheet_key("t2652b"), {"title": "Vuelos Madrid-Roma", "items": []})
    sheet.apply_action("append", {"sheet": "t2652b", "items": FULL})
    assert [i["title"] for i in sheet.view_data("t2652b")["items"]] == ["Ryanair 110 EUR"]


def test_a_correction_rejudges_the_clipped_rows_already_on_the_sheet():
    from widgets.results import category_gate
    sheet.store.save(sheet.sheet_key("t2652c"), {"title": "Vuelos baratos", "items": [
        {"title": "Buscar vuelos de Logroño (RJL) a…", "price": "88 €"}, {"title": "Ryanair 110 EUR", "price": "110"}]})
    assert category_gate.recheck("t2652c", "que sea Madrid–Roma, directo") == 1
    assert [i["title"] for i in sheet.view_data("t2652c")["items"]] == ["Ryanair 110 EUR"]


def test_a_sheet_with_no_route_asked_is_untouched():
    sheet.apply_action("present", {"sheet": "t2652d", "title": "Planes en Madrid", "items": FULL})
    assert len(sheet.view_data("t2652d")["items"]) == 3
