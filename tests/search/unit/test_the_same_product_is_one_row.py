"""The same product is one row: a second copy (same model code under the same brand, or the same whole title at the
same price) is turned away at the door, and the copy with more facts is the one kept (node 2.698).

search-buy-tv ES (2026-10-14): «LG 55QNED70B6C» was two rows of one sheet, and the turn read both out. A row sent
again with its own title and link is an UPDATE (the sheet merges it), never a duplicate; a title cut with «…» is
not a whole name, so two listings sharing its start stay.
"""
from __future__ import annotations

from search import row_dedupe, row_fit
from widgets.results import data as sheet

LG_A = {"title": "LG 55QNED70B6C - Smart TV QNED", "price": "579 €", "url": "https://a.test/1"}
LG_B = {"title": "LG 55QNED70B6C Smart TV 4K 2025", "price": "599 €", "url": "https://b.test/2",
        "facts": [{"label": "Panel", "value": "QNED"}]}


def test_a_model_code_twice_is_one_row_and_the_fuller_one_stays():
    on, off = row_fit.split([LG_A, LG_B, {"title": "Sony Bravia 8"}], "", [])
    assert [r["title"] for r in on] == [LG_B["title"], "Sony Bravia 8"]
    assert off[0]["title"] == LG_A["title"] and "the same product" in off[0]["why"]


def test_same_title_and_price_is_a_copy_but_a_cut_title_and_another_brand_are_not():
    seat = {"title": "Seat León 1.6 TDI 2018", "price": "11.500 €"}
    assert len(row_dedupe.split([seat, {**seat, "url": "https://x.test/2"}], [])[0]) == 1
    cut = [{"title": "5YR/100K WARRANTY INCLUDED! 15…", "price": "$11,995", "url": f"https://c.test/{i}"}
           for i in range(2)]
    assert len(row_dedupe.split(cut, [])[0]) == 2
    gpus = [{"title": "Lenovo Legion 5 RTX4070", "price": "1"}, {"title": "ASUS ROG Strix RTX4070", "price": "2"}]
    assert len(row_dedupe.split(gpus, [])[0]) == 2


def test_an_append_of_a_copy_is_turned_away_and_a_resend_is_an_update():
    sheet.apply_action("present", {"sheet": "t2698", "title": "TVs", "items": [LG_A]})
    res = sheet.apply_action("append", {"sheet": "t2698", "items": [LG_B]})
    assert [i["title"] for i in sheet.view_data("t2698")["items"]] == [LG_A["title"]]
    assert "the same product" in res.get("note_for_worker", "")
    sheet.apply_action("append", {"sheet": "t2698", "items": [{**LG_A, "facts": [{"label": "Size", "value": "55\""}]}]})
    items = sheet.view_data("t2698")["items"]
    assert len(items) == 1 and items[0].get("facts")
