"""A row whose title is the page's own facet, filter or navigation label, without a price and a link, is not a
candidate (node 2.697).

search-buy-washing-machine US (2026-10-14): three browser extractions landed only page chrome — «Washer Capacity
(cu. ft.) 45 to Up», «Minimum Price» at «$700», «Contact Us», «Shop by Brand», «ENERGY STAR Certified and 4.0…» —
and the sheet ended on that last one as its only candidate. The worker is told why at the door.
"""
from __future__ import annotations

from search import fragment_fit, row_fit
from widgets.results import data as sheet

MEASURED = [{"title": "Less than $25", "price": "$25", "url": ""},
            {"title": "Minimum Price", "price": "$700", "url": ""},
            {"title": "Washer Capacity (cu. ft.) 45 to Up", "price": "$700", "url": ""},
            {"title": "Dismiss 45 cu ft and up", "price": "$700", "url": ""},
            {"title": "Contact Us", "price": "", "url": "https://www.dshomeappliances.test/locations/ocean-ave"},
            {"title": "Shop by Brand", "price": "", "url": "https://www.dshomeappliances.test/brands"},
            {"title": "ENERGY STAR Certified and 4.0…", "price": "", "url": ""},
            {"title": "Sort by: Price Low to High", "price": "", "url": ""},
            {"title": "1,204 results for \"washer\"", "price": "", "url": ""}]
OFFERS = [{"title": "LG WM4000HWA 4.5 cu. ft. Front Load Washer", "price": "$699", "url": "https://x.test/p/1"},
          {"title": "Samsung WF45T6000AW 4.5 cu ft", "price": "", "url": ""},
          {"title": "TV wall mount, fits 55 to 65 inch", "price": "$30", "url": "https://x.test/p/2"}]


def test_every_measured_fragment_is_off_and_every_offer_stays():
    on, off = row_fit.split(MEASURED + OFFERS, "", ["Washers"])
    assert sorted(o["title"] for o in off) == sorted(r["title"] for r in MEASURED)
    assert [r["title"] for r in on] == [r["title"] for r in OFFERS]
    assert all("not an offer" in o["why"] for o in off)


def test_a_chrome_title_with_a_price_and_a_link_stays():
    assert not fragment_fit.why_off({"title": "Deals", "price": "$499", "url": "https://x.test/p/9"})
    assert fragment_fit.why_off({"title": "Deals", "price": "", "url": "https://x.test/deals"})


def test_the_worker_is_told_at_the_door():
    res = sheet.apply_action("present", {"sheet": "t2697", "title": "Washers", "items": MEASURED[:3] + OFFERS[:1]})
    kept = [i["title"] for i in sheet.view_data("t2697")["items"]]
    assert len(kept) == 1 and kept[0].startswith("LG WM4000HWA")
    assert "not an offer" in res.get("note_for_worker", "") and "Do not re-add" in res["note_for_worker"]
