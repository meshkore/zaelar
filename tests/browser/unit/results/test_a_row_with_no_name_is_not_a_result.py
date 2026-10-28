"""A row with no NAME is not a result: the sheet's door folds it into the named row before it, or drops it (V2-831 T-01, node 4.322).

2026-10-28, the operator's screenshot of a streaming errand: six of the thirteen rows were titled with the price text
a scraper lifted from the offer page («6,69 € /mes - Ahorra un 25%<br>», raw markup included, the price repeated in
`price`), and an empty `{}` came with them. The door only checked that `title` was non-empty, so each became a card
whose monogram was «1». The rule is STRUCTURAL — a name comes before its amount — so it is asked here in other
currencies and scripts, and a title that is a bare number with no currency («1984») stays a name.
"""
from __future__ import annotations

import json
from pathlib import Path

from widgets.results import clean, data as sheet

EVIDENCE = json.loads((Path(__file__).parent / "fixtures" / "sheet_with_poor_rows_2026_10_28.json").read_text())


def test_the_recorded_sheet_keeps_only_named_rows_and_the_prices_become_its_offer_options():
    items = clean._clean_items(EVIDENCE["items"])
    titles = [it["title"] for it in items]
    assert len(items) == 7, titles                                   # 6 earlier rows + the offer; no price row, no {}
    assert not any(t[:1].isdigit() for t in titles), titles
    offer = items[-1]
    assert offer["title"] == "SkyShowtime"
    assert [f["label"] for f in offer["facts"]] == ["6,69 €", "6,99 €", "8,99 €", "10,49 €", "10,99 €", "13,99 €"]
    assert offer["facts"][0]["value"] == "/mes - Ahorra un 25%"


def test_markup_never_reaches_a_text_slot():
    it = clean._clean_item({"title": "<b>Hotel</b> Sol &amp; Mar<br>", "subtitle": "a<br/>b",
                            "price": "120 €<br>", "lines": ["x<br>", "<p></p>"]})
    assert it["title"] == "Hotel Sol & Mar" and it["subtitle"] == "a b" and it["price"] == "120 €"
    assert it["lines"] == ["x"]
    assert "<" not in json.dumps(clean._clean_items(EVIDENCE["items"]), ensure_ascii=False)


def test_the_rule_is_structural_any_currency_any_script():
    named = [{"title": "KTC H27P22S — $254.98", "price": "$254.98"}, {"title": "東京タワー 展望台", "price": "¥1,200"},
             {"title": "1984"}, {"title": "2 Fast 2 Furious"}, {"title": "Ryanair · 49 €"}]
    nameless = [{"title": "$19.99/mo - save 20%", "price": "$19.99"}, {"title": "¥1,200 から"},
                {"title": "13,99 €"}, {"title": "£5 per month"}, {"title": "1.299 zł / miesiąc", "price": "1.299 zł"}]
    assert all(clean._split(clean._clean_item(r))[2] for r in named), named
    assert not any(clean._split(clean._clean_item(r))[2] for r in nameless), nameless


def test_a_nameless_row_with_no_named_row_before_it_is_dropped():
    assert clean._clean_items([{"title": "9,99 € /mes", "price": "9,99 €"}, {}]) == []


def test_both_doors_apply_it():
    sheet.apply_action("present", {"sheet": "t01door", "items": EVIDENCE["items"]})
    assert len(sheet.view_data("t01door")["items"]) == 7
    sheet.apply_action("append", {"sheet": "t01door", "items": [{"title": "Max", "price": "9,99 €"},
                                                                 {"title": "9,99 € /mes", "price": "9,99 €"}]})
    got = sheet.view_data("t01door")["items"]
    assert [it["title"] for it in got][-1] == "Max" and len(got) == 8
    assert got[-1]["facts"] == [{"label": "9,99 €", "value": "/mes"}]
