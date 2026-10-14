"""A correction that restates his ceiling re-judges the rows already on the sheet (node 2.670).

search-buy-laptop ES (2026-10-14): «esos que me pasas están por encima de 1.800, no me sirven» — the rows stayed,
and two turns later the same over-ceiling rows were offered again. The correction reaches `category_gate.recheck`;
the rows above it leave the list for the Rejected tab with their reason, the ones within it stay.
"""
from __future__ import annotations

from widgets.results import category_gate, data as sheet

ROWS = [{"title": "Apple MacBook Pro 14 M5 1TB", "price": "2.229 €"},
        {"title": "MacBook Pro M5 14 16GB", "price": "1.999 €"},
        {"title": "MacBook Pro 14 M5 eBay", "price": "1.663 €"}]


def test_a_correction_that_states_the_ceiling_moves_the_rows_above_it():
    sheet.store.save(sheet.sheet_key("t2670a"), {"title": "MacBook Pro M5", "items": list(ROWS)})
    n = category_gate.recheck("t2670a", "Perdona, pero esos que me pasas están por encima de 1.800, no me sirven.")
    view = sheet.view_data("t2670a")
    assert n == 2 and [i["price"] for i in view["items"]] == ["1.663 €"]
    assert all("1,800" in r["why"] for r in view["rejected"])


def test_a_ceiling_relayed_in_our_words_rejudges_too():
    sheet.store.save(sheet.sheet_key("t2670b"), {"title": "MacBook Pro M5", "items": list(ROWS)})
    assert category_gate.recheck("t2670b", "El operador quiere precio máximo de 1.800 €", relayed=True) == 2


def test_a_correction_without_a_ceiling_leaves_the_prices_alone():
    sheet.store.save(sheet.sheet_key("t2670c"), {"title": "MacBook Pro M5", "items": list(ROWS)})
    assert category_gate.recheck("t2670c", "mírame el plazo de envío del de 1.663 €") == 0
