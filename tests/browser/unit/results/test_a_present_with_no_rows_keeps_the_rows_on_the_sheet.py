"""A `present` that carries no rows keeps the rows on the sheet (demo pass 132, 2026-10-15).

S1 «so how did the monitors go, show me»: the model promised without a call and the promise repair sent
`results:present {tab: results}` — no `items` key at all. `present` replaced the four monitors with nothing, and S3
«open the one that's the best deal» then answered «I can't find that result in the sheet». A present with no `items`
key re-shows what is there; an explicit `items: []` is still a search that found nothing.
"""
import pytest

from widgets import store
from widgets.results import data as D  # noqa: I001 — data first: actions imports it back
from widgets.results import actions as A

ROWS = [{"title": "Dell S2725QC", "price": "$345.99", "url": "https://example.com/dell"},
        {"title": "LG 27UP650K-W", "price": "$239.99", "url": "https://example.com/lg"}]


@pytest.fixture
def sheet(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    A._a_present("present", {"title": "27-inch 4K monitors", "items": ROWS}, "s1")
    assert len(D.view_data("s1")["items"]) == 2
    return "s1"


def test_a_present_with_no_items_key_re_shows_the_rows(sheet):
    A._a_present("present", {"tab": "results"}, sheet)
    v = D.view_data(sheet)
    assert [i["title"] for i in v["items"]] == ["Dell S2725QC", "LG 27UP650K-W"] and v["title"] == "27-inch 4K monitors"
    assert A._a_detail("detail", {"index": 1}, sheet)["ok"] is True


def test_an_explicit_empty_list_still_empties_it(sheet):
    A._a_present("present", {"items": []}, sheet)
    assert D.view_data(sheet)["items"] == []
