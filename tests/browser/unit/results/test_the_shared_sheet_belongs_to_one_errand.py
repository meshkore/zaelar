"""The SHARED results sheet belongs to one errand at a time: a browser push that names its errand but no sheet takes
the shared sheet over instead of appending onto another errand's rows (V2-831 T-01).

2026-10-28: a streaming-offer errand's browser findings were pushed with no sheet and appended under six school-
canteen rows an earlier web search had left on the shared sheet. `intake.push(errand=…)` is the seam; the producers
that know the errand (`nucleo/dispatch/prepare.py`, `widgets/navegador/owner_actions.py`) pass it.
"""
from __future__ import annotations

from widgets.results import data as sheet, intake

OLD = [{"title": "Comedores Escolares - Educacyl", "url": "https://www.educa.jcyl.es/"}]
NEW = [{"title": "SkyShowtime", "price": "6,99€", "url": "https://www.skyshowtime.com/es"}]


def _titles():
    return [it["title"] for it in sheet.view_data("")["items"]]


def test_an_errand_push_replaces_rows_it_does_not_own_and_then_accumulates_its_own():
    sheet.apply_action("present", {"items": OLD, "sources": [{"name": "web search"}]})
    assert intake.push(NEW, errand="task-7") == 1
    assert _titles() == ["SkyShowtime"]
    assert [s["name"] for s in sheet.view_data("")["sources"]] == [], "the old errand's sources went with its rows"
    intake.push([{"title": "Max", "price": "9,99 €", "url": "https://max.com"}], errand="task-7")
    assert _titles() == ["SkyShowtime", "Max"]
    intake.push([{"title": "Filmin", "url": "https://filmin.es"}], errand="task-8")
    assert _titles() == ["Filmin"]


def test_a_push_with_no_errand_still_accumulates_and_an_errand_sheet_is_untouched():
    sheet.apply_action("present", {"items": OLD})
    intake.push(NEW)                                                 # the operator browsing by hand
    assert _titles() == [OLD[0]["title"], "SkyShowtime"]
    sheet.apply_action("present", {"sheet": "own-1", "items": OLD})
    intake.push(NEW, sheet="own-1", errand="task-9")
    assert [it["title"] for it in sheet.view_data("own-1")["items"]] == [OLD[0]["title"], "SkyShowtime"]


def test_a_present_keeps_the_owner():
    intake.push(NEW, errand="task-3")
    sheet.apply_action("present", {"items": NEW + [{"title": "Max", "url": "https://max.com"}]})
    intake.push([{"title": "Filmin", "url": "https://filmin.es"}], errand="task-3")
    assert _titles() == ["SkyShowtime", "Max", "Filmin"]
