"""«Open the best deal» lands on the sheet that HOLDS that item, when the call names no sheet (demo pass 107).

S2/S3: two sheets were open — the base one with a quick search, and the errand's instance with its monitors. The
model called `detail {title: "<the errand's top pick>"}` on the base id; the base had no such row and answered «no
encuentro ese resultado», twice, and the comparison went to the wrong sheet. When no sheet is named and exactly
one other sheet holds that title, the detail opens there. An index alone, or a title two sheets hold, stays put.
"""
from __future__ import annotations

from widgets.results import data

QUICK = [{"title": "Philips 27E1N1800AE 4K", "price": "$199"}, {"title": "LG 27US500-W Ultrafine", "price": "$229"}]
ERRAND = [{"title": "Dell 27 Plus S2725QC", "price": "$329.99"}, {"title": "KTC M27P6S", "price": "$399.99"}]


def _two_sheets(monkeypatch, tmp_path):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    assert data.apply_action("present", {"items": QUICK}).get("ok")
    assert data.apply_action("present", {"items": ERRAND, "sheet": "05929c-ls1"}).get("ok")


def test_a_title_only_another_sheet_holds_opens_there(monkeypatch, tmp_path):
    _two_sheets(monkeypatch, tmp_path)
    got = data.apply_action("detail", {"title": "Dell 27 Plus S2725QC"})
    assert got.get("ok") and got["detail"].startswith("Dell"), got
    assert data.view_data("05929c-ls1").get("view") == "detail"
    assert data.view_data("").get("view") != "detail", "the base sheet was not what he pointed at"


def test_a_title_on_the_base_sheet_stays_there(monkeypatch, tmp_path):
    _two_sheets(monkeypatch, tmp_path)
    assert data.apply_action("detail", {"title": "LG 27US500-W Ultrafine"}).get("ok")
    assert data.view_data("").get("view") == "detail"


def test_a_named_sheet_is_never_second_guessed(monkeypatch, tmp_path):
    _two_sheets(monkeypatch, tmp_path)
    assert not data.apply_action("detail", {"title": "Philips 27E1N1800AE 4K", "q": "05929c-ls1"}).get("ok")
