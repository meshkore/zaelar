"""A row named with the decoration the sheet printed beside it is still that row (node 4.240).

Demo pass 63, S3 (2026-09-30): «open the one that's the best deal» over the compare view arrived as
`detail {title: "KTC H27P22S — $254.98"}` — the line the compare view shows, title and price — and the sheet
answered «no encuentro ese resultado» twice, while the turn said «Done.».
"""
from widgets.results import data as sheet

ITEMS = [{"title": "Samsung ViewFinity S7 27in 4K"}, {"title": "KTC H27P22S"}, {"title": "LG 27UP650K-W"}]


def test_the_title_with_its_price_resolves_to_the_row():
    assert sheet._find(ITEMS, "KTC H27P22S — $254.98")["title"] == "KTC H27P22S"
    assert sheet._find(ITEMS, "LG 27UP650K-W · $299")["title"] == "LG 27UP650K-W"


def test_a_reference_that_contains_a_whole_title_names_it_once():
    assert sheet._find(ITEMS, "the KTC H27P22S one, cheapest")["title"] == "KTC H27P22S"


def test_nothing_is_guessed():
    assert sheet._find(ITEMS, "Dell U2723QE — $399") is None
    assert sheet._find([{"title": "Hotel Sol"}, {"title": "Hotel Sol Playa"}], "hotel sol playa y hotel sol") is None
