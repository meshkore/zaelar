"""The worker is told which rows broke his ceiling or his place and why, and a row it re-adds stays out (node 2.674).

search-buy-laptop ES (2026-10-14): the same over-ceiling rows came back turn after turn. The door's reply now names
each rejected row with its reason and says not to re-add it; the Rejected tab keeps the reason; and an `append` of
the same row meets the same gate, so it never returns to the list.
"""
from __future__ import annotations

from widgets.results import data as sheet

ASK = "Find me an apartment to rent in Austin, two bedrooms, under $1,900 a month"
ROWS = [{"title": "The Asher", "price": "$1,390", "url": "https://x.test/Texas/Austin-Apartments/asher"},
        {"title": "Kelsey 2BR", "price": "$2,080/mo", "url": "https://x.test/Texas/Austin-Apartments/kelsey"},
        {"title": "Azola Avery Centre", "price": "$1,183", "url": "https://x.test/Texas/Round-Rock-Apartments/azola"}]


def test_the_reply_and_the_rejected_tab_carry_the_reason():
    res = sheet.apply_action("present", {"sheet": "t2674a", "title": "Austin rentals", "asked": ASK, "items": ROWS})
    note = res.get("note_for_worker", "")
    assert "Rejected tab" in note and "Do not re-add" in note
    assert "1,900 ceiling" in note and "Round Rock, not Austin" in note
    whys = {r["title"]: r["why"] for r in sheet.view_data("t2674a")["rejected"]}
    assert set(whys) == {"Kelsey 2BR", "Azola Avery Centre"}


def test_a_readded_row_meets_the_same_door():
    sheet.apply_action("present", {"sheet": "t2674b", "title": "Austin rentals", "asked": ASK, "items": ROWS})
    res = sheet.apply_action("append", {"sheet": "t2674b", "items": [ROWS[1], ROWS[2]]})
    assert [i["title"] for i in sheet.view_data("t2674b")["items"]] == ["The Asher"]
    assert len(sheet.view_data("t2674b")["rejected"]) == 2                     # filed once, not twice
    assert "Do not re-add" in res.get("note_for_worker", "")
