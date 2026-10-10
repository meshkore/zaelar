"""«Play the second one» with the results on Home and an empty queue plays the second RESULT (V2-781).

Measured in `la-cola-de-video-con-palabras-imprecisas__us` (2026-10-10): the search filled Home, the queue was
empty, the model called `play_item {"n": 2}` — `play_item` read neither `n` nor the search band, answered «No
encuentro ese vídeo en la lista», and the turn escalated to a worker that took 90 s to press play.
"""
from widgets.youtube import data as yt

from .test_a_media_search_fills_the_list_not_the_sheet import sandbox  # noqa: F401 — the shared fixture


def test_play_item_over_an_empty_queue_plays_that_search_result(sandbox):  # noqa: F811
    yt.apply_action("search", {"query": "videos de paella"})
    r = yt.apply_action("play_item", {"n": 2})
    assert r["ok"], r
    assert yt.view_data()["videoId"] == "BBBBBBBBBB2"


def test_play_item_still_plays_from_the_queue_when_there_is_one(sandbox):  # noqa: F811
    yt.apply_action("search", {"query": "videos de paella"})
    yt.apply_action("add_results", {"items": "1,3"})
    r = yt.apply_action("play_item", {"n": 2})
    assert r["ok"] and yt.view_data()["videoId"] == "CCCCCCCCCC3", "the queue's second, not the band's"
