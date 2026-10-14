"""A row priced above the ceiling he stated is not a candidate (node 2.669).

search-buy-laptop ES (2026-10-14): with «por menos de 1.800 euros», the turn twice offered three rows all above it
(2.229 €, 1.999 €, 2.949 €; then 1.899 €, 3.099 €, 2.539 €). Judged at `ceiling_fit` with a 3 % tolerance, on the
lowest amount the price states, in the same currency and unit; a row with no price stays.
"""
from __future__ import annotations

from search import ceiling_fit, row_fit

LAPTOP = "Búscame un MacBook Pro M5 por menos de 1.800 euros, nuevo o reacondicionado."
ABOVE = ["2.229 €", "1.999 €", "2.949 €", "1.899 €", "3.099 €", "2.539 €"]
WITHIN = ["1.663 €", "1.700 €", "1.599 €", "1.850 €", "1.663 € + 37 € envío", "Antes 2.199 € ahora 1.749 €", ""]


def _rows(prices):
    return [{"title": f"Apple MacBook Pro 14 M5 #{i}", "price": p} for i, p in enumerate(prices)]


def test_the_six_measured_rows_above_the_ceiling_are_off_and_the_rest_stay():
    on, off = row_fit.split(_rows(ABOVE + WITHIN), LAPTOP, ["MacBook Pro M5"])
    assert sorted(o["title"] for o in off) == sorted(r["title"] for r in _rows(ABOVE))
    assert [r["price"] for r in on] == WITHIN
    assert all("1,800 ceiling" in o["why"] for o in off)


def test_another_currency_or_unit_is_not_compared():
    ceil = ceiling_fit.asked_ceiling("under $1,900 a month")
    assert ceiling_fit.why_off({"price": "$2,080/mo"}, ceil)
    assert ceiling_fit.why_off({"price": "$2,080"}, ceil)                 # an unmarked rent is the month's
    assert not ceiling_fit.why_off({"price": "2.080 €"}, ceil)
    assert not ceiling_fit.why_off({"price": "$24,000/yr"}, ceil)
    night = ceiling_fit.asked_ceiling("a hotel under $300 a night")
    assert ceiling_fit.why_off({"price": "$350/night"}, night)
    assert not ceiling_fit.why_off({"price": "$1,138 total"}, night)      # the stay, not the night
    assert not ceiling_fit.why_off({"price": "$350"}, night)              # on a booking site, likely the stay


def test_a_range_is_judged_by_its_lowest_amount_and_no_ceiling_judges_nothing():
    ceil = ceiling_fit.asked_ceiling("under $1,900 a month")
    assert not ceiling_fit.why_off({"price": "$1,107 - $2,080"}, ceil)
    assert row_fit.split(_rows(ABOVE), "Búscame un MacBook Pro M5", [])[1] == []
