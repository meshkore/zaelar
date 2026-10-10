"""«Put on a few videos, back to back» builds the QUEUE from the search and plays its first one (V2-781).

Measured in `la-cola-de-video-con-palabras-imprecisas__us` (2026-10-10 20:11): the reply promised «I'll line up a
few Maradona videos for you and start the first one», the turn's ops were `load` alone, and «play the second one»
failed three times running because there was no queue — it first existed on turn 6, when the operator dictated it.
The widget half: `queue_search` paints the band, queues its first n in the band's order and plays the first, so a
positional reference means the same video against either surface; a single `load` still builds nothing.
"""
import json
from pathlib import Path

from widgets.youtube import data as yt

from .test_a_media_search_fills_the_list_not_the_sheet import sandbox  # noqa: F401 — the shared fixture


def _ids(rows):
    return [r.get("videoId") for r in rows]


def test_queue_search_queues_the_results_in_order_and_plays_the_first(sandbox):  # noqa: F811
    r = yt.apply_action("queue_search", {"query": "Maradona videos"})
    assert r["ok"], r
    v = yt.view_data()
    assert _ids(v["list"]) == ["AAAAAAAAAA1", "BBBBBBBBBB2", "CCCCCCCCCC3"], "the queue is the band, in its order"
    assert _ids(v["search_results"]) == _ids(v["list"]), "band and queue coincide, so «the second» is one video"
    assert v["videoId"] == "AAAAAAAAAA1" and v["pos"] == 0 and v["paused"] is False
    assert r["queued"][0] == "Paella de marisco en 20 minutos" and r["count"] == 3


def test_the_second_one_resolves_against_the_built_queue(sandbox):  # noqa: F811
    yt.apply_action("queue_search", {"query": "Maradona videos"})
    assert yt.apply_action("play_item", {"item": "2"})["ok"]
    assert yt.view_data()["videoId"] == "BBBBBBBBBB2"
    r = yt.apply_action("play_result", {"item": 3})      # the band kept its numbers, and they are the queue's
    assert r["ok"], r
    assert yt.view_data()["videoId"] == "CCCCCCCCCC3" and yt.view_data()["pos"] == 2


def test_an_existing_queue_is_appended_to_never_replaced(sandbox):  # noqa: F811
    yt.apply_action("add", {"url": "https://www.youtube.com/watch?v=ZZZZZZZZZZ9", "title": "His own"})
    r = yt.apply_action("queue_search", {"query": "Maradona videos", "n": 2})
    assert r["ok"], r
    v = yt.view_data()
    assert _ids(v["list"]) == ["ZZZZZZZZZZ9", "AAAAAAAAAA1", "BBBBBBBBBB2"]
    assert v["videoId"] == "AAAAAAAAAA1" and v["pos"] == 1, "the first NEW row plays, not his own"


def test_a_single_play_builds_no_queue(sandbox):  # noqa: F811
    yt.apply_action("load", {"query": "Maradona goal"})
    v = yt.view_data()
    assert v["videoId"] == "AAAAAAAAAA1" and v["list"] == [], "one video asked, one video loaded — no queue"
    yt.apply_action("search", {"query": "Maradona videos"})
    assert yt.view_data()["list"] == [], "a search to CHOOSE from never queues either (V2-632)"


def test_the_manifest_declares_it_and_it_produces_sound():
    man = json.loads((Path(yt.__file__).parent / "manifest.json").read_text(encoding="utf-8"))
    assert "queue_search" in man["actions"]
    assert "queue_search" in man["runtime"]["produce"]
