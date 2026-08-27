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


def test_search_action_fills_the_list_and_touches_no_player_state(sandbox):
    # A video is PLAYING; the search must not interrupt it — V2-366's law extended to searching.
    yt.apply_action("load", {"url": "https://www.youtube.com/watch?v=ZZZZZZZZZZ9", "title": "Sonando"})
    before = yt.view_data()
    r = yt.apply_action("search", {"query": "videos de paella"})
    assert r["ok"] and len(r["added"]) == 3 and r["count"] == 3
    after = yt.view_data()
    assert after["videoId"] == before["videoId"] == "ZZZZZZZZZZ9", "a search must never change what is playing"
    assert after.get("paused") == before.get("paused")
    assert [it["videoId"] for it in after["list"]] == ["AAAAAAAAAA1", "BBBBBBBBBB2", "CCCCCCCCCC3"]


def test_search_dedups_against_what_the_list_already_has(sandbox):
    yt.apply_action("add", {"url": "https://youtu.be/AAAAAAAAAA1", "title": "Ya estaba"})
    r = yt.apply_action("search", {"query": "videos de paella"})
    assert r["ok"] and len(r["added"]) == 2, "an already-listed video is not a new finding"
    vids = [it["videoId"] for it in yt.view_data()["list"]]
    assert vids.count("AAAAAAAAAA1") == 1


def test_an_empty_search_is_said_not_swallowed(sandbox, monkeypatch):
    monkeypatch.setattr(yt, "_search_many", lambda q, n=5: [])
    r = yt.apply_action("search", {"query": "zzz nada"})
    assert r["ok"] is False and r["error"] == "no_video" and r["message"]
    assert yt.view_data().get("adding") == "", "the visible searching state must turn off even on failure"


def test_a_search_without_query_asks_for_one(sandbox):
    r = yt.apply_action("search", {})
    assert r["ok"] is False and r["error"] == "no_query"
