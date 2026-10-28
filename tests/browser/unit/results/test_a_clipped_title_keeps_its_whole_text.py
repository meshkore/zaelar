"""Node 2.685 — a row whose title the card clips keeps the whole title beside it (`full_title`).

search-buy-sofa__us (2026-10-14): the listing was «Premium 3-Seat Sofa – Excellent Condition – Only 6 Months Used –
$350»; the sheet stored «Premium 3-Seat Sofa – Excellent…» and dropped the rest. The next turn the model retracted a
TRUE claim («I shouldn't have said "six months used" — that detail isn't actually in the listing») and the judge
called it invented. The card still paints the clipped `title`; a reader of the row reads
the whole one. A title that fits gets no copy, and a re-clean keeps it.

Disarm: drop the `setdefault("full_title", …)` in `data._clean_item` → the cap test goes red.
"""
from __future__ import annotations

from widgets.results import data

LONG = "Premium 3-Seat Sofa – Excellent Condition – Only 6 Months Used – $350"
#: V2-797 — the card no longer clips a listing's name to a layout budget (it clamps on screen); the only cut left
#: is the STORAGE cap of a field, so the copy is now kept for a title past that cap.
HUGE = " · ".join([LONG] * 6)


def test_a_listing_title_is_stored_whole():
    it = data._clean_item({"title": LONG, "price": "350 USD"})
    assert it["title"] == LONG and "full_title" not in it


def test_a_title_past_the_storage_cap_keeps_the_listing_words_in_full_title():
    it = data._clean_item({"title": HUGE, "price": "350 USD"})
    assert it["title"].endswith("…") and len(it["title"]) < len(HUGE)
    assert it["full_title"] == HUGE


def test_a_reclean_keeps_the_whole_one():
    once = data._clean_item({"title": HUGE})
    assert data._clean_item(once) == once

