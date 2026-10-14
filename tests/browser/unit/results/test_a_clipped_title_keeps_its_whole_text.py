"""Node 2.685 — a row whose title the card clips keeps the whole title beside it (`full_title`).

search-buy-sofa__us (2026-10-14): the listing was «Premium 3-Seat Sofa – Excellent Condition – Only 6 Months Used –
$350»; the sheet stored «Premium 3-Seat Sofa – Excellent…» and dropped the rest. The next turn the model retracted a
TRUE claim («I shouldn't have said "six months used" — that detail isn't actually in the listing») and the judge
called it invented. The card still paints the clipped `title`; a reader of the row (`claim_backing.row_text`,
the row-claims guard) reads the whole one. A title that fits gets no copy, and a re-clean keeps it.

Disarm: drop the `setdefault("full_title", …)` in `data._clean_item` → the first test goes red.
"""
from __future__ import annotations

from widgets.results import data

LONG = "Premium 3-Seat Sofa – Excellent Condition – Only 6 Months Used – $350"


def test_a_clipped_title_keeps_the_listing_words_in_full_title():
    it = data._clean_item({"title": LONG, "price": "350 USD"})
    assert it["title"].endswith("…") and len(it["title"]) < len(LONG)
    assert it["full_title"] == LONG


def test_a_title_that_fits_gets_no_copy_and_a_reclean_keeps_the_whole_one():
    assert "full_title" not in data._clean_item({"title": "Danish-Style Apartment Sofa", "price": "249"})
    once = data._clean_item({"title": LONG})
    assert data._clean_item(once) == once


def test_the_row_reader_sees_the_whole_title():
    from nucleo.flash import claim_backing as B
    assert "Only 6 Months Used" in B.row_text(data._clean_item({"title": LONG}))
