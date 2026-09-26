"""«Compare them visually» over a results sheet already on screen (demo run, 2026-09-26): the agent promised to put
the three monitors side by side and had no way to — a template could only arrive with `present`, re-sending
every item. `layout` re-shapes what is there, keeps every item, and returns to the results list."""
import pytest


@pytest.fixture
def rs(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.results import data as d
    assert d.apply_action("present", {"items": [{"title": "Dell S2721QS", "price": "$214"},
                                                {"title": "LG 27UP850K", "price": "$289"},
                                                {"title": "MSI 27 4K", "price": "$163"}]}).get("ok") is not False
    return d


def test_the_sheet_takes_a_new_shape_and_keeps_its_items(rs):
    got = rs.apply_action("layout", {"layout": "tile"})
    assert got["ok"] and got["layout"] == "tile" and got["items"] == 3
    v = rs.view_data()
    assert v["layout"] == "tile" and [i["title"] for i in v["items"]][0] == "Dell S2721QS"


def test_an_unknown_shape_teaches_the_choices(rs):
    got = rs.apply_action("layout", {"layout": "pie chart"})
    assert not got["ok"] and "tile" in got["error"]


def test_the_action_is_declared_so_the_brain_can_choose_it():
    import json
    import pathlib
    m = json.loads((pathlib.Path(__file__).resolve().parents[4] / "widgets/results/manifest.json").read_text())
    assert "compare them visually" in m["actions"]["layout"]["desc"]
    assert m["actions"]["detail"]["desc"].startswith("OPENS ONE result in full («open the best value option»")
