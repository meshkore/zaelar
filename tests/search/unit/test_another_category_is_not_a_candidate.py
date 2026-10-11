"""A row of another product category is never a candidate (V2-782 T3.3) — golden over the recorded sheets.

search-buy-used-car ES and EN (2026-10-11): the listing pass filled the sheet with car parts, model trains, a 1:43
truck, a price guide, a matchcover and a «View Nationwide Inventory» page, and the turn named them as cars three
times. The rule lives at the sheet's door (`present`/`append`), so it is tested there and on the pure judge; every
other recorded sheet of the family is the false-positive guard: none of its rows may be judged off.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from search import category

SHEETS = Path(__file__).resolve().parents[1] / "fixtures" / "sheets"
CAR_ES = "Búscame un coche de segunda mano, que no sea muy viejo, diésel, y que no pase de 12 mil euros."
CAR_EN = "Find me a used car, diesel or hybrid, under 60k miles and under $14,000, and give me the top 3."


def _sheet(name: str) -> dict:
    return json.loads(next(SHEETS.glob(name + "*.json")).read_text(encoding="utf-8"))


def test_the_spanish_junk_leaves_and_every_car_stays():
    d = _sheet("search-buy-used-car__es__results--fe89cc-ls1-junk")
    on, off = category.split(d["items"], CAR_ES, [d["title"]])
    gone = {o["title"] for o in off}
    for junk in ("piezas de coches de segunda mano", "Guardabarros delantero derecho…",
                 "Cursor 1923 1:43 Daimler Benz LKW…", "Locomotora American Flyer Comet…",
                 "8 vagones de pasajeros centrales…", "Motor diésel BACHMANN HO placa de…", "+ Vehículos del profesional"):
        assert junk in gone, junk
    kept = {o["title"] for o in on}
    assert {"Fiat Tipo", "BMW 730", "Peugeot 3008", "Opel Insignia 2021 1.5 dci 122 cv"} <= kept
    assert all(o["why"] for o in off)


def test_the_english_junk_leaves_and_every_car_stays():
    d = _sheet("search-buy-used-car__en__results--eafc58-ls1-junk")
    on, off = category.split(d["items"], CAR_EN, [d["title"]])
    gone = {o["title"] for o in off}
    for junk in ("Catalog Nissan Laurel Used Car…", "2009 Subaru TRIBECA High Horn", "Lote 1056 Matchcover Centro de…",
                 "NADA Official Used Car Guide…", "View Nationwide Inventory", "Amplificador de audio para…"):
        assert junk in gone, junk
    assert {"2015 BMW I3 REX Edition 1", "2017 Kia Niro EX Hybrid - 1…", "2008 Toyota Prius 1"} <= {o["title"] for o in on}


@pytest.mark.parametrize("path", sorted(p.name for p in SHEETS.glob("*.json")
                                        if not p.stem.endswith(("-junk", "-mixed", "-offsubject"))))
def test_no_row_of_a_clean_recorded_sheet_is_judged_off(path):
    d = json.loads((SHEETS / path).read_text(encoding="utf-8"))
    crit = d.get("criteria") or {}
    on, off = category.split(d.get("items") or [], "", [d.get("title"), crit.get("goal")] + list(crit.get("changes") or []))
    assert not off, off


def test_a_class_he_asked_for_is_his_category():
    rows = [{"title": "Guardabarros delantero derecho Seat Ibiza", "price": "45 €"}]
    on, off = category.split(rows, "Busco piezas de segunda mano para mi Seat Ibiza, un guardabarros", [])
    assert on and not off


def test_an_accessory_offered_with_the_thing_is_not_another_category():
    rows = [{"title": "Kymco Agility 125 con accesorios", "price": "1.200 €"}]
    on, off = category.split(rows, "Búscame una moto de segunda mano de 125", [])
    assert on and not off


def test_a_rental_or_an_insurance_ask_is_not_judged_as_buying_a_vehicle():
    rows = [{"title": "Avis Car Rental — AUS airport", "price": "$45"}]
    assert category.split(rows, "best rated car rental at the airport", [])[1] == []
    assert category.split([{"title": "GEICO", "price": "$124"}], "compare car insurance quotes", [])[1] == []


def test_the_sheet_door_files_off_rows_as_rejected_and_tells_the_worker():
    from widgets.results import data as sheet
    res = sheet.apply_action("present", {"sheet": "t2510", "title": "Coches diésel hasta 12.000 €", "asked": CAR_ES,
                                         "items": [{"title": "Locomotora American Flyer Comet", "price": "151.24"},
                                                   {"title": "Peugeot 3008", "price": "€ 7.999"}]})
    view = sheet.view_data("t2510")
    assert [i["title"] for i in view["items"]] == ["Peugeot 3008"]
    assert any(r["title"].startswith("Locomotora") and r["why"] for r in view["rejected"])
    assert "NOT what he asked for" in res["note_for_worker"]
    res = sheet.apply_action("append", {"sheet": "t2510", "items": [{"title": "Guardabarros delantero", "price": "30"}]})
    assert [i["title"] for i in sheet.view_data("t2510")["items"]] == ["Peugeot 3008"], "append is gated too"


def test_the_category_marker_alone_rejects_a_row_the_price_and_the_make_would_let_through():
    rows = [{"title": "Maqueta Ford Mustang 1967 escala 1:18 coleccionista", "price": "1.200 €"},
            {"title": "Catálogo oficial Mercedes-Benz 2019", "price": "900 €"},
            {"title": "Ford Mustang 1967 restaurado", "price": "11.900 €"}]
    on, off = category.split(rows, CAR_ES, [])
    assert [o["title"] for o in on] == ["Ford Mustang 1967 restaurado"]
    assert {o["why"].split(" (")[0] for o in off} == {"a toy or scale model", "a guide, catalogue or collectible"}
