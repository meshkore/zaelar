"""«Open the best value option» opens the card whose badge says BEST VALUE.

Measured 2026-09-27 (verification after the demo pass; open since the morning's v5 as «S3 falla el detail»): the
sheet's four monitors carry the badges «Best value», «Best reviewed», «Cheapest», «Best for gaming». The model
passed the sentence as `index`; `_find` read only titles and ordinals, found nothing, and the detail failed.
"""
from widgets.results import data

ITEMS = [{"title": "Samsung ViewFinity S7 (S70H)", "badge": "Best value"},
         {"title": "LG 27US500-W Ultrafine", "badge": "Best reviewed"},
         {"title": "Philips 27E1N1800A", "badge": "Cheapest"}]


def test_the_badge_he_names_finds_its_card():
    assert data._find(ITEMS, "", "Open the best value option.")["title"].startswith("Samsung")
    assert data._find(ITEMS, "the cheapest one")["title"].startswith("Philips")


def test_titles_and_ordinals_still_win_and_a_string_number_counts():
    assert data._find(ITEMS, "LG 27US500-W Ultrafine")["badge"] == "Best reviewed"
    assert data._find(ITEMS, "", 3)["title"].startswith("Philips")
    assert data._find(ITEMS, "", "2")["title"].startswith("LG")


def test_nothing_named_is_still_nothing():
    assert data._find(ITEMS, "", "the one with the red stand") is None


def test_detail_reads_the_row_under_the_key_other_cards_use(monkeypatch, tmp_path):
    """Demo pass 2026-09-28 (S3): «open the one that's the best deal» arrived as `detail {"item": "Dell S2725QS"}`
    — the row key the map and youtube cards declare — and the sheet answered «no encuentro ese resultado»."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    assert data.apply_action("present", {"items": ITEMS}).get("ok")
    got = data.apply_action("detail", {"item": "LG 27US500-W Ultrafine"})
    assert got.get("ok") and got["detail"].startswith("LG"), got
