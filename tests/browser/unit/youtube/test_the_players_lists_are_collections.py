"""V2-776 L2 · The player's search results and its list are collections a verifier can read (node 4.233).

«Play the fifth one» ends with result #5 playing. The card held `search_results` and `list` in its view and
declared neither, so «youtube playing result #5» could not be attested; `play_result`'s postcondition (videoId
changed, not paused) reads the scalars, and the collections let a spec name the ROW («the CBS News one»).
"""
import pytest

RESULTS = [{"videoId": "a1", "title": "Starship Flight 5 — full launch"},
           {"videoId": "b2", "title": "Starship booster catch, CBS News"},
           {"videoId": "c3", "title": "Starship IFT-4 highlights"}]


@pytest.fixture
def yt(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.youtube import data
    db = data._load()
    db["search_results"] = list(RESULTS)
    db["search_query"] = "spacex starship tests"
    store.save(data.WID, db)
    return data


def test_the_results_are_a_read_only_collection_from_the_view(yt):
    from widgets import rows
    assert rows.ops_for("youtube", "search_results") == ("list",)
    assert rows.ops_for("youtube", "list") == ("list",)
    assert [r["videoId"] for r in rows.select("youtube", "search_results", {"title~": "cbs"})] == ["b2"]


def test_a_spec_can_name_the_row_and_the_scalar(yt):
    from nucleo import verify
    assert verify.check({"widget": "youtube", "collection": "search_results", "where": {"title~": "cbs news"}}) is True
    assert verify.check({"widget": "youtube", "field": "search_query", "has": "starship"}) is True
