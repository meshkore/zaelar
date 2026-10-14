"""Both doors of the sheet (`present`, `append`) hand what they saved to the first-rows notice (node 2.681)."""
from __future__ import annotations

from nucleo.turn import first_rows_notice as frn
from widgets.results import data as sheet


def test_present_and_append_call_the_notice(monkeypatch):
    seen = []
    monkeypatch.setattr(frn, "landed", lambda s, items: seen.append((s, [i["title"] for i in items])) or False)
    row = {"title": "Sunny 2BR on Valencia St", "price": "$3,400", "url": "https://zillow.com/1"}
    sheet.apply_action("present", {"sheet": "door-t1", "title": "Flats", "items": [row]})
    sheet.apply_action("append", {"sheet": "door-t1", "items": [{**row, "title": "Loft on 24th St",
                                                                  "url": "https://zillow.com/2"}]})
    assert seen[0] == ("door-t1", ["Sunny 2BR on Valencia St"])
    assert seen[1] == ("door-t1", ["Sunny 2BR on Valencia St", "Loft on 24th St"])


def test_a_sheet_with_no_live_errand_schedules_nothing(monkeypatch):
    monkeypatch.setattr(frn, "_errand_of", lambda s: None)
    assert frn.landed("door-t2", [{"title": "X", "url": "https://x"}]) is False
