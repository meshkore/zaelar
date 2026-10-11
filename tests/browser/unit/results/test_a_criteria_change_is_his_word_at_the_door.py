"""A criteria change the turn recorded as HIS is read at the sheet's door like his own words (node 2.557).

three-tasks-at-once (ES, 2026-10-11 11:34). The monitor's «27 al menos» reached the sheet, when it reached it at all,
as `criteria.changes` — «correcciones del operador», written by the turn from his sentence. The gate read subjects and
specs from `asked` ONLY (so that a sheet title the model wrote is never taken for his ask), and the 24" rows stayed.
A correction is not a title: `category_gate._own` reads `asked` plus the recorded changes.
"""
from __future__ import annotations

from widgets.results import data as sheet


def _seed(sid: str) -> None:
    sheet.store.save(sheet.sheet_key(sid), {"title": "Monitores de segunda mano", "items": [
        {"title": 'LG UltraGear 24" IPS 144Hz', "price": "60 €"}, {"title": 'Fujitsu P27-8 TE Pro 27" QHD', "price": "59 €"},
        {"title": 'Asus VA24DQ 23,8" IPS', "price": "50 €"}]})


def test_a_recorded_change_rejects_the_rows_already_there():
    _seed("t2557a")
    sheet.apply_action("criteria", {"sheet": "t2557a", "criteria": {"changes": ["que sea de 27 pulgadas al menos"]}})
    view = sheet.view_data("t2557a")
    assert [i["title"] for i in view["items"]] == ['Fujitsu P27-8 TE Pro 27" QHD']
    assert {r["title"] for r in view["rejected"]} == {'LG UltraGear 24" IPS 144Hz', 'Asus VA24DQ 23,8" IPS'}


def test_and_a_later_append_meets_the_same_floor():
    _seed("t2557b")
    sheet.apply_action("criteria", {"sheet": "t2557b", "criteria": {"changes": ["al menos 27"]}})
    sheet.apply_action("append", {"sheet": "t2557b", "items": [{"title": 'MSI 24" Full HD 200Hz', "price": "74 €"},
                                                               {"title": 'LG 27" 144Hz IPS', "price": "85 €"}]})
    titles = [i["title"] for i in sheet.view_data("t2557b")["items"]]
    assert 'MSI 24" Full HD 200Hz' not in titles and 'LG 27" 144Hz IPS' in titles


def test_a_title_the_model_wrote_is_still_not_his_spec():
    sheet.store.save(sheet.sheet_key("t2557c"), {"title": 'Best-Value 27" Monitors', "items": []})
    sheet.apply_action("append", {"sheet": "t2557c", "items": [{"title": 'Dell 24" P2419H', "price": "37"}]})
    assert [i["title"] for i in sheet.view_data("t2557c")["items"]] == ['Dell 24" P2419H']
