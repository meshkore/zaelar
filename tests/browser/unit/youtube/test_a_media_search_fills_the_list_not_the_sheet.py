"""A media search lands in the PLAYER's list, not in the results sheet (V2-402).

Measured live by the operator (2026-08-27): asking zaelar to FIND videos ended in the generic results sheet —
six real trailer titles filed as information rows, zero of them playable — because "search several videos"
had no owner: `play_video` loaded exactly ONE best match and everything plural fell through to
`escalate_to_slowbrain`, whose `lista` surface IS the sheet. The operator's rule: content you watch or listen
to is channelled through its dedicated widget; the sheet is for information (a hotel whose page has videos is
still information).

This file covers the widget half: the `search` action puts SEVERAL candidates in the list, and inherits
V2-366's law — nothing a search does may start playback or touch the player.
"""
import io
import urllib.request

import pytest

from widgets.youtube import data as yt
from widgets import store

# A results page carries every candidate; each videoId is repeated many times (thumbs, params). The parser
# must dedup by id and keep the PAGE order.
_HTML = (
    '{"videoRenderer":{"videoId":"AAAAAAAAAA1",'
    '"title":{"runs":[{"text":"Paella de marisco en 20 minutos"}]},'
    '"ownerText":{"runs":[{"text":"Cocina Facil"}]},'
    '"publishedTimeText":{"simpleText":"hace 3 d\\u00edas"}}}'
    '{"thumbnail":{"videoId":"AAAAAAAAAA1"}}'
    '{"videoRenderer":{"videoId":"BBBBBBBBBB2",'
    '"title":{"runs":[{"text":"Paella valenciana tradicional"}]},'
    '"ownerText":{"runs":[{"text":"Arroces del Levante"}]},'
    '"publishedTimeText":{"simpleText":"hace 1 semana"}}}'
    '{"videoRenderer":{"videoId":"CCCCCCCCCC3",'
    '"title":{"runs":[{"text":"El secreto del socarrat"}]}}}'
)


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=6: io.BytesIO(_HTML.encode("utf-8")))


def test_search_many_parses_several_distinct_videos_in_page_order(sandbox):
    hits = yt._search_many("videos de paella", 5)
    assert [h["videoId"] for h in hits] == ["AAAAAAAAAA1", "BBBBBBBBBB2", "CCCCCCCCCC3"]
    assert hits[0]["title"] == "Paella de marisco en 20 minutos"
    assert hits[0]["channel"] == "Cocina Facil"
    assert hits[2]["title"] == "El secreto del socarrat"  # a hit without channel/date still lands


def test_search_many_respects_n(sandbox):
    assert len(yt._search_many("paella", 2)) == 2


def test_search_action_fills_the_dashboard_and_touches_no_player_or_queue_state(sandbox):
    # A video is PLAYING; the search must not interrupt it — V2-366's law extended to searching. And since
    # V2-632 the results are the DASHBOARD's band, never queue rows: results are something to choose from,
    # the queue is what he chose.
    yt.apply_action("load", {"url": "https://www.youtube.com/watch?v=ZZZZZZZZZZ9", "title": "Sonando"})
    before = yt.view_data()
    r = yt.apply_action("search", {"query": "videos de paella"})
    assert r["ok"] and len(r["results"]) == 3 and r["count"] == 3
    after = yt.view_data()
    assert after["videoId"] == before["videoId"] == "ZZZZZZZZZZ9", "a search must never change what is playing"
    assert after.get("paused") == before.get("paused")
    assert after["list"] == before["list"] == [], "a search must never write into the queue (V2-632)"
    assert [it["videoId"] for it in after["search_results"]] == ["AAAAAAAAAA1", "BBBBBBBBBB2", "CCCCCCCCCC3"]
    assert after["search_query"] == "videos de paella"


def test_a_new_search_replaces_the_previous_results(sandbox):
    yt.apply_action("search", {"query": "videos de paella"})
    yt.apply_action("search", {"query": "otra paella"})
    d = yt.view_data()
    assert d["search_query"] == "otra paella"
    assert len(d["search_results"]) == 3, "results are a view of the LAST question, never an archive"


def test_play_result_loads_that_video_and_add_results_feeds_the_queue_deduped(sandbox):
    yt.apply_action("search", {"query": "videos de paella"})
    r = yt.apply_action("play_result", {"item": "2"})
    assert r["ok"] and yt.view_data()["videoId"] == "BBBBBBBBBB2"
    # «añade los tres primeros a la cola» — and adding what the queue already holds is not a new row.
    yt.apply_action("add", {"url": "https://youtu.be/AAAAAAAAAA1", "title": "Ya estaba"})
    r = yt.apply_action("add_results", {"items": "1,3"})
    assert r["ok"] and len(r["added"]) == 1, "an already-queued video is not a new addition"
    vids = [it["videoId"] for it in yt.view_data()["list"]]
    assert vids == ["AAAAAAAAAA1", "CCCCCCCCCC3"]
    # «todos» works, out-of-range numbers refuse honestly, and clear_search empties the band.
    r = yt.apply_action("add_results", {"items": "all"})
    assert r["ok"]
    assert yt.apply_action("play_result", {"item": "9"})["error"] == "bad_index"
    yt.apply_action("clear_search", {})
    d = yt.view_data()
    assert d["search_results"] == [] and d["search_query"] == ""
    assert yt.apply_action("play_result", {"item": "1"})["error"] == "no_results"


def test_an_empty_search_is_said_not_swallowed(sandbox, monkeypatch):
    monkeypatch.setattr(yt, "_search_many", lambda q, n=5: [])
    r = yt.apply_action("search", {"query": "zzz nada"})
    assert r["ok"] is False and r["error"] == "no_video" and r["message"]
    assert yt.view_data().get("adding") == "", "the visible searching state must turn off even on failure"


def test_a_search_without_query_asks_for_one(sandbox):
    r = yt.apply_action("search", {})
    assert r["ok"] is False and r["error"] == "no_query"


def test_follow_channel_with_no_name_follows_the_current_videos_author(sandbox):
    # V2-632: «este vídeo me gusta — sigue a este canal» names nobody; the CURRENT video's channel is the
    # referent (the V2-609 class: a required argument the sentence never fills).
    yt.apply_action("load", {"url": "https://www.youtube.com/watch?v=ZZZZZZZZZZ9", "title": "Sonando"})
    db = yt._load(); db["channel"] = "MUNDO DE LA VELA"
    from widgets import store as _st
    _st.save(yt.WID, db)
    r = yt.apply_action("follow_channel", {})
    assert r["ok"] and r["channel"] == "MUNDO DE LA VELA"
    # with NOTHING playing and no name, the honest refusal stays
    yt.apply_action("close", {})
    r = yt.apply_action("follow_channel", {})
    assert r["ok"] is False and r["error"] == "no_channel"
