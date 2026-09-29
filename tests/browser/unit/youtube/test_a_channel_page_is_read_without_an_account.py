# 2026-09-29 — the followed channels become CARDS (picture, subscribers, videos) and a click opens the
# channel's own PAGE (videos, lives, shorts, playlists), paged, cached and refreshed on every visit. All of it
# is read from the public pages a browser sees; nothing signs in and nothing subscribes on YouTube.
#
# No network here: `channels._get` is replaced by canned pages shaped like the real ones (measured against
# youtube.com the same day), so what is under test is OUR parsing, caching and merging.
from __future__ import annotations

import json
import time

import pytest

from widgets.youtube import channels, data


def _page(lockups=(), tabs=("videos", "streams", "shorts", "playlists"), header=True, grid_token="GRIDTOK",
          other_token="CHIPTOK", shorts=()):
    d = {"header": {}, "contents": {"tabs": []}}
    if header:
        d["header"] = {"pageHeaderViewModel": {
            "title": {"dynamicTextViewModel": {"text": {"content": "Canal de Prueba"}}},
            "image": {"decoratedAvatarViewModel": {"avatar": {"avatarViewModel": {"image": {"sources": [
                {"url": "https://yt3.example/a=s72", "width": 72},
                {"url": "https://yt3.example/a=s160", "width": 160}]}}}}},
            "metadata": {"contentMetadataViewModel": {"metadataRows": [
                {"metadataParts": [{"text": {"content": "@canalprueba"}}]},
                {"metadataParts": [{"text": {"content": "77,2\xa0mil suscriptores"}},
                                   {"text": {"content": "1,2\xa0mil vídeos"}}]}]}}}}
    # tab titles are TRANSLATED on the real page; the section is recognised by its URL
    d["contents"]["tabs"] = [{"tabRenderer": {"title": "Título traducido %d" % i, "endpoint": {"commandMetadata": {
        "webCommandMetadata": {"url": "/@canalprueba/" + t}}}}} for i, t in enumerate(("featured",) + tuple(tabs))]
    grid = {"richGridRenderer": {"contents": [{"richItemRenderer": {"content": {"lockupViewModel": lk}}}
                                              for lk in lockups]
                                 + [{"richItemRenderer": {"content": {"shortsLockupViewModel": s}}} for s in shorts]
                                 + ([{"continuationItemRenderer": {"continuationEndpoint": {
                                     "continuationCommand": {"token": grid_token}}}}] if grid_token else [])}}
    d["contents"]["grid"] = grid
    # a token OUTSIDE the grid (the «about» panel, the sort chips) must never be taken for «load more»
    d["about"] = {"continuationItemRenderer": {"continuationEndpoint": {"continuationCommand": {"token": other_token}}}}
    return ('<script>var ytInitialData = ' + json.dumps(d) + ';</script>'
            '"INNERTUBE_API_KEY":"k","INNERTUBE_CLIENT_VERSION":"2.0"')


def _video(vid, title, views="2,3\xa0K", age="hace 1 h", dur="14:56", live=False):
    badges = [{"thumbnailBadgeViewModel": {"text": "EN DIRECTO" if live else dur}}]
    return {"contentId": vid, "contentType": "LOCKUP_CONTENT_TYPE_VIDEO",
            "contentImage": {"thumbnailViewModel": {"overlays": [{"thumbnailBottomOverlayViewModel": {"badges": badges}}]}},
            "metadata": {"lockupMetadataViewModel": {"title": {"content": title}, "metadata": {
                "contentMetadataViewModel": {"metadataRows": [{"metadataParts": [
                    {"text": {"content": views}}, {"text": {"content": age}}]}]}}}}}


def _playlist(pid, title, n):
    return {"contentId": pid, "contentType": "LOCKUP_CONTENT_TYPE_PLAYLIST",
            "contentImage": {"collectionThumbnailViewModel": {"primaryThumbnail": {"thumbnailViewModel": {
                "image": {"sources": [{"url": "https://i.ytimg.com/pl.jpg", "width": 480}]},
                "overlays": [{"thumbnailBadgeViewModel": {"text": "%d vídeos" % n}}]}}}},
            "metadata": {"lockupMetadataViewModel": {"title": {"content": title}}}}


# ── the numbers and dates, in both languages the card speaks ─────────────────────────────────────────────

@pytest.mark.parametrize("text,n", [
    ("77.2K subscribers", 77200), ("77,2 mil suscriptores", 77200), ("2,3\xa0K", 2300), ("15\xa0K", 15000),
    ("10 mil vídeos", 10000), ("10K videos", 10000), ("1,234 views", 1234), ("1.234 visualizaciones", 1234),
    ("1,2 M", 1200000), ("6 vídeos", 6), ("", 0), ("sin número", 0)])
def test_a_count_reads_as_a_number_in_spanish_and_english(text, n):
    assert channels.count(text) == n


@pytest.mark.parametrize("text,s", [
    ("1h ago", 3600), ("2 days ago", 172800), ("Streamed 5 days ago", 432000), ("3 weeks ago", 1814400),
    ("hace 1 h", 3600), ("hace 1 d", 86400), ("Emitido hace 5 días", 432000), ("hace 2 meses", 5184000),
    ("hace 7 minutos", 420), ("hace 1 año", 31536000), ("2,3 K", -1), ("", -1)])
def test_a_relative_date_reads_as_seconds_in_spanish_and_english(text, s):
    assert channels.age_seconds(text) == s


# ── the page ─────────────────────────────────────────────────────────────────────────────────────────────

def test_the_header_gives_the_card_facts_and_the_sections_come_from_their_URLS():
    head = channels._header(channels._initial_data(_page(tabs=("videos", "shorts"))))
    assert head["subscribers"] == 77200 and head["videos"] == 1200
    assert head["handle"] == "@canalprueba" and head["avatar"].endswith("s160"), "the largest picture"
    assert head["tabs"] == ["videos", "shorts"], "only the sections the channel HAS, found by URL"


def test_videos_lives_and_playlists_become_flat_rows():
    now = int(time.time())
    d = channels._initial_data(_page([_video("AAAAAAAAAA1", "Uno"), _video("AAAAAAAAAA2", "Dos", live=True,
                                                                           age="", views="120 espectadores"),
                                      _playlist("PL1", "Mi lista", 6)]))
    rows = channels._items("videos", d, now)
    assert [r["id"] for r in rows] == ["AAAAAAAAAA1", "AAAAAAAAAA2", "PL1"]
    v = rows[0]
    assert (v["title"], v["views"], v["age"], v["duration"], v["live"]) == ("Uno", 2300, 3600, "14:56", False)
    assert v["ts"] == now - 3600
    assert rows[1]["live"] is True
    assert rows[2]["kind"] == "playlist" and rows[2]["count"] == 6 and rows[2]["thumb"].endswith("pl.jpg")


def test_load_more_takes_the_GRIDS_token_never_a_neighbours():
    d = channels._initial_data(_page([_video("AAAAAAAAAA1", "Uno")]))
    assert channels._cont_token(d) == "GRIDTOK"
    d = channels._initial_data(_page([_video("AAAAAAAAAA1", "Uno")], grid_token=""))
    assert channels._cont_token(d) == "", "a grid with no token of its own has no next page"


def test_a_refresh_prepends_what_is_new_and_never_drops_what_was_there():
    old = [{"id": "B", "title": "b"}, {"id": "C", "title": "c", "ts": 5, "exact": True}]
    fresh = [{"id": "A", "title": "a"}, {"id": "C", "title": "c v2", "ts": 9}]
    rows, new = channels._merge(old, fresh)
    assert [r["id"] for r in rows] == ["A", "C", "B"] and new == 1
    assert rows[1]["title"] == "c v2", "what changed is updated…"
    assert rows[1]["ts"] == 5 and rows[1]["exact"], "…but an exact time learned from the feed is kept"


# ── the actions, end to end over canned pages ────────────────────────────────────────────────────────────

_RSS = ('<feed><entry><yt:videoId>AAAAAAAAAA1</yt:videoId><published>2026-09-29T10:00:00+00:00</published>'
        '</entry></feed>')


@pytest.fixture
def yt(monkeypatch, tmp_path):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))        # a fresh state AND a fresh page cache per test
    store._last_hash.pop("youtube", None)
    pages = {"first": [_video("AAAAAAAAAA1", "Uno"), _video("AAAAAAAAAA2", "Dos", age="hace 2 d")]}
    calls = []

    def fake_get(url):
        calls.append(url)
        if "feeds/videos.xml" in url:
            return _RSS
        if "/results?" in url:
            ch = {"channelRenderer": {"channelId": "UCtest", "title": {"simpleText": "Canal de Prueba"},
                                      "thumbnail": {"thumbnails": [{"url": "//yt3.example/s88", "width": 88}]},
                                      "videoCountText": {"simpleText": "77,2 mil suscriptores"},
                                      "subscriberCountText": {"simpleText": "@canalprueba"}}}
            return '<script>var ytInitialData = ' + json.dumps({"c": [ch]}) + ';</script>'
        return _page(pages["first"])
    monkeypatch.setattr(channels, "_get", fake_get)
    monkeypatch.setattr(channels, "_continue", lambda tok: channels._initial_data(
        _page([_video("AAAAAAAAAA%d" % i, "V%d" % i) for i in range(3, 40)], grid_token=""))
        if tok == "GRIDTOK" else {})
    data.apply_action("follow_channel", {"channel": "Canal de Prueba"})
    return pages, calls


def test_the_cards_learn_their_facts_once_and_never_subscribe_anywhere(yt):
    _, calls = yt
    assert data.view_data()["channel_cards"][0]["resolved"] is False
    data.apply_action("sync_channels", {})
    card = data.view_data()["channel_cards"][0]
    assert (card["id"], card["subscribers"], card["videos"]) == ("UCtest", 77200, 1200)
    assert card["avatar"].startswith("https://")
    n = len(calls)
    data.apply_action("sync_channels", {})
    assert len(calls) == n, "a channel just resolved is not fetched again on the next repaint"
    assert not any("subscribe" in u or "youtubei/v1/subscription" in u for u in calls), \
        "the subscription is OURS — nothing may call YouTube's subscribe"


def test_walking_in_flags_what_is_new_and_the_feed_gives_the_exact_time(yt):
    pages, _ = yt
    assert data.apply_action("open_channel", {"channel": "prueba"})["ok"]
    data.apply_action("refresh_channel", {})
    pg = data.view_data()["channel_page"]
    assert pg["tab"] == "videos" and pg["tabs"] == ["videos", "streams", "shorts", "playlists"]
    assert [i["id"] for i in pg["items"]] == ["AAAAAAAAAA1", "AAAAAAAAAA2"]
    assert pg["items"][0]["exact"] and pg["items"][0]["ts"] == 1790676000, "RSS wins over «hace 1 h»"
    assert pg["new_ids"] == [], "the first visit has nothing to compare against"
    pages["first"] = [_video("NEWNEWNEW01", "Recién salido")] + pages["first"]
    data.apply_action("refresh_channel", {})
    pg = data.view_data()["channel_page"]
    assert pg["new_ids"] == ["NEWNEWNEW01"]
    assert [i["id"] for i in pg["items"]][:3] == ["NEWNEWNEW01", "AAAAAAAAAA1", "AAAAAAAAAA2"]


def test_more_pages_through_the_cache_and_the_state_stays_small(yt):
    data.apply_action("open_channel", {"channel": "prueba"})
    data.apply_action("refresh_channel", {})
    data.apply_action("channel_more", {})
    pg = data.view_data()["channel_page"]
    assert len(pg["items"]) == 39 and not pg["has_more"]
    from widgets import store
    state = store.load("youtube", {})
    assert "sections" not in json.dumps(state.get("channel_view")), \
        "the pages live in their own cache file; the state only points at the open one"


def test_a_section_and_a_playlist_open_and_the_crumbs_go_back(yt):
    pages, _ = yt
    data.apply_action("open_channel", {"channel": "prueba"})
    pages["first"] = [_playlist("PL1", "Mi lista", 6)]
    assert data.apply_action("channel_tab", {"tab": "playlists"})["ok"]
    pg = data.view_data()["channel_page"]
    assert pg["tab"] == "playlists" and pg["items"][0]["kind"] == "playlist"
    pages["first"] = [_video("AAAAAAAAAA7", "Dentro de la lista")]
    data.apply_action("channel_playlist", {"playlist": "PL1", "title": "Mi lista"})
    pg = data.view_data()["channel_page"]
    assert pg["playlist"]["id"] == "PL1" and pg["items"][0]["id"] == "AAAAAAAAAA7"
    data.apply_action("channel_playlist", {"playlist": ""})
    assert "playlist" not in data.view_data()["channel_page"]
    data.apply_action("close_channel", {})
    assert data.view_data()["channel_page"] == {}


def test_a_bad_section_or_no_open_channel_is_said_not_swallowed(yt):
    assert data.apply_action("refresh_channel", {})["error"] == "no_channel_open"
    data.apply_action("open_channel", {"channel": "prueba"})
    assert data.apply_action("channel_tab", {"tab": "comunidad"})["error"] == "bad_tab"
    assert data.apply_action("open_channel", {"channel": "nadie"})["error"] == "not_followed"


def test_youtube_not_answering_keeps_what_was_cached(yt, monkeypatch):
    data.apply_action("open_channel", {"channel": "prueba"})
    data.apply_action("refresh_channel", {})

    def down(url):
        raise OSError("offline")
    monkeypatch.setattr(channels, "_get", down)
    r = data.apply_action("refresh_channel", {})
    assert r["ok"] is False and r["error"] == "fetch_failed"
    assert len(data.view_data()["channel_page"]["items"]) == 2
