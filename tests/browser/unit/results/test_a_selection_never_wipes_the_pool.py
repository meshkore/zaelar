"""The list is a SELECTION from what the hunt gathered; a `present` that narrows it never loses the rest (node 12.837).

search-buy-used-car ES (V2-835, 2026-11-02): the sheet held 35 candidate cars; he asked for «the three best», the
worker's final `present` carried its 3 picks and replaced the list — and when he asked for at least 10 there was
nothing left to give: the 35 were gone. Now every candidate that passed the door stays in `pool`; `present` sets the
list, `append {from_pool: n}` brings the next n back through the same door, and an explicit `items: []` (a search that
found nothing, demo pass 132) still empties the sheet.
"""
from __future__ import annotations

from widgets.results import digest
from widgets.results import data as sheet


def _car(i: int) -> dict:
    return {"title": f"Mercedes-Benz GLC 220d 4MATIC 20{10 + i % 10}", "price": f"{20 + i}.{i % 10}90 €",
            "url": f"https://www.autoscout24.es/anuncios/glc-220d-{i:03d}"}


ALL = [_car(i) for i in range(1, 36)]


def _titles(sid: str) -> list[str]:
    return [i["title"] + i["url"] for i in sheet.view_data(sid)["items"]]


def test_the_three_best_keep_the_other_32_in_the_pool():
    sid = "t2837a"
    sheet.apply_action("present", {"sheet": sid, "title": "GLC 220d", "items": ALL[:20]})
    sheet.apply_action("append", {"sheet": sid, "items": ALL[20:]})
    res = sheet.apply_action("present", {"sheet": sid, "items": [ALL[7], ALL[2], ALL[30]]})
    view = sheet.view_data(sid)
    assert [i["url"] for i in view["items"]] == [ALL[7]["url"], ALL[2]["url"], ALL[30]["url"]], "the order he got"
    assert len(view["pool"]) == 35 and res["pool"] == 32 and "from_pool" in res["pool_note"]
    assert "32 more candidates" in digest.one(view)


def test_more_results_start_from_the_pool():
    sid = "t2837b"
    sheet.apply_action("present", {"sheet": sid, "title": "GLC 220d", "items": ALL})
    sheet.apply_action("present", {"sheet": sid, "items": ALL[:3]})
    res = sheet.apply_action("append", {"sheet": sid, "from_pool": 7})
    urls = [i["url"] for i in sheet.view_data(sid)["items"]]
    assert res["ok"] and urls == [c["url"] for c in ALL[:10]]


def test_what_a_later_exclusion_rules_out_never_comes_back_from_the_pool():
    sid = "t2837c"
    flexi = {**ALL[5], "subtitle": "Negro · FLEXICAR COSLADA (Madrid)"}
    sheet.apply_action("present", {"sheet": sid, "title": "GLC 220d", "items": ALL[:5] + [flexi] + ALL[6:12]})
    sheet.apply_action("present", {"sheet": sid, "items": ALL[:3]})
    sheet.apply_action("criteria", {"sheet": sid, "criteria": {"excluded": ["Flexicar"]}})
    assert all("FLEXICAR" not in (r.get("subtitle") or "") for r in sheet.view_data(sid)["pool"])
    sheet.apply_action("append", {"sheet": sid, "from_pool": 20})
    assert len(sheet.view_data(sid)["items"]) == 11


def test_an_explicit_empty_present_still_empties_the_sheet():
    sid = "t2837d"
    sheet.apply_action("present", {"sheet": sid, "title": "GLC 220d", "items": ALL[:6]})
    sheet.apply_action("present", {"sheet": sid, "items": []})
    view = sheet.view_data(sid)
    assert view["items"] == [] and not view.get("pool")
    assert not sheet.apply_action("append", {"sheet": sid, "from_pool": 5})["ok"]


def test_a_present_without_items_reshows_and_keeps_the_pool():
    sid = "t2837e"
    sheet.apply_action("present", {"sheet": sid, "title": "GLC 220d", "items": ALL[:8]})
    sheet.apply_action("present", {"sheet": sid, "items": ALL[:2]})
    sheet.apply_action("present", {"sheet": sid, "tab": "results"})
    view = sheet.view_data(sid)
    assert len(view["items"]) == 2 and len(view["pool"]) == 8
