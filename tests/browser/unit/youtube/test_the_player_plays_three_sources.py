"""The video player stops being YouTube-only (V2-638): a library file and a live torrent play in it too.

`data.py` has said since V2-632 that «`source` travels per row because the widget is provider-agnostic by
design — today every row says "youtube", and a second source is a value, not a schema change». These are the
cases that make that true, plus the two latent defects that had to be closed BEFORE non-YouTube rows could
exist at all:

  · `availability.blocked_ids` keyed the blocklist on `videoId`, and every non-YouTube row carries `""` — so
    one blocked local file would have put `""` in the set, which the queue filter reads as "matches
    everything", silently skipping every local item forever.
  · `swap_to` located the playing row by `videoId`, so with two local rows (both `""`) it reported the FIRST
    one as the position of whichever was actually playing.
"""
from __future__ import annotations

import pytest

from widgets.youtube import availability, sources


@pytest.fixture
def lib(monkeypatch, tmp_path):
    """A real library rooted in a temp workspace — `item_from_library` reads the disk."""
    from library import paths
    from nucleo import workspace as ws
    monkeypatch.setattr(ws, "root", lambda: tmp_path)
    paths._ov_cache.update(path=None, mtime=None, data={})
    paths.ensure()
    yield paths
    paths._ov_cache.update(path=None, mtime=None, data={})


# ── 1 · the source discriminator, and the stale-src trap ────────────────────────────────────────────────────

def test_a_row_without_a_source_is_youtube():
    """Every row written before this existed carries no `source` and must keep playing exactly as it did."""
    assert sources.source_of({}) == "youtube"
    assert sources.source_of({"videoId": "abc"}) == "youtube"
    assert sources.source_of({"source": "nonsense"}) == "youtube"


def test_only_library_and_torrent_rows_stream():
    assert sources.is_stream({"source": "local"}) is True
    assert sources.is_stream({"source": "torrent"}) is True
    assert sources.is_stream({"source": "youtube"}) is False


def test_carrying_a_youtube_row_CLEARS_a_previous_src():
    """The trap: a stale `src` left by the previous row is how a YouTube video ends up playing the last
    local file's bytes. `carry` always writes both keys, never only the one that applies."""
    db = {}
    sources.carry(db, {"source": "local", "src": "/api/library/stream?path=video/a.mp4"})
    assert db["source"] == "local" and db["src"].endswith("a.mp4")
    sources.carry(db, {"videoId": "abc"})
    assert db["source"] == "youtube" and db["src"] == ""


# ── 2 · a row built from the agent's own library ────────────────────────────────────────────────────────────

def test_a_playable_library_video_becomes_a_row(lib):
    (lib.dir_for("video") / "film.mp4").write_bytes(b"x")
    it = sources.item_from_library("video/film.mp4")
    assert it["source"] == "local" and it["videoId"] == ""
    assert it["src"].startswith("/api/library/stream?path=")
    assert it["title"] == "film.mp4"


def test_an_unplayable_or_missing_file_yields_no_row(lib):
    (lib.dir_for("video") / "film.mkv").write_bytes(b"x")     # a real video the browser cannot decode
    assert sources.item_from_library("video/film.mkv") == {}
    assert sources.item_from_library("video/nope.mp4") == {}


def test_play_local_says_it_is_unplayable_and_offers_the_download(lib):
    (lib.dir_for("video") / "film.mkv").write_bytes(b"x")
    r = sources.play_local({}, "video/film.mkv")
    assert r["ok"] is False and r["download_url"]            # the pendrive way round, not a dead end


def test_play_local_on_a_missing_file_says_so(lib):
    r = sources.play_local({}, "video/nope.mp4")
    assert r["ok"] is False and "biblioteca" in r["error"]


# ── 3 · the torrent tool reached FROM the player (the operator's requirement) ───────────────────────────────

def test_play_torrent_refuses_when_the_client_is_switched_off(monkeypatch):
    from connectors.torrent import service
    monkeypatch.setattr(service, "available", lambda: False)
    monkeypatch.setattr(service, "unavailable_reason", lambda: "está desactivado")
    r = sources.play_torrent({}, "some film")
    assert r["ok"] is False and "desactivado" in r["error"]


def test_play_torrent_builds_a_streaming_row(monkeypatch):
    from connectors.torrent import service
    monkeypatch.setattr(service, "available", lambda: True)
    monkeypatch.setattr(service, "search_and_play",
                        lambda q, **k: {"ok": True, "id": "HASH", "title": "The Film"})
    r = sources.play_torrent({}, "the film")
    assert r["ok"]
    it = r["item"]
    assert it["source"] == "torrent" and it["src"] == "/api/torrent/stream/HASH"
    assert it["torrent_id"] == "HASH" and it["videoId"] == ""


def test_play_torrent_asks_for_a_VIDEO_and_passes_keep_through(monkeypatch):
    from connectors.torrent import service
    seen = {}
    monkeypatch.setattr(service, "available", lambda: True)
    monkeypatch.setattr(service, "search_and_play",
                        lambda q, **k: seen.update(k) or {"ok": True, "id": "H", "title": q})
    sources.play_torrent({}, "the film", keep=True)
    assert seen["want"] == "video" and seen["keep"] is True


def test_play_torrent_with_an_id_adopts_it_without_searching_again(monkeypatch):
    """The Descargas widget's own «▶» hands over an id already downloading/finished — no new search, no new
    magnet, the SAME session handle."""
    from connectors.torrent import service
    monkeypatch.setattr(service, "available", lambda: True)
    monkeypatch.setattr(service, "status", lambda rid: {"ok": True, "id": rid, "name": "The Film"})
    hit = []
    monkeypatch.setattr(service, "search_and_play", lambda q, **k: hit.append(1) or {"ok": False})
    monkeypatch.setattr(service, "add_magnet", lambda m, **k: hit.append(1) or {"ok": False})
    r = sources.play_torrent({}, id="HASH")
    assert not hit
    assert r["ok"] and r["item"]["source"] == "torrent" and r["item"]["torrent_id"] == "HASH"
    assert r["item"]["title"] == "The Film"


def test_play_torrent_with_an_id_that_is_no_longer_active_refuses(monkeypatch):
    from connectors.torrent import service
    monkeypatch.setattr(service, "available", lambda: True)
    monkeypatch.setattr(service, "status", lambda rid: {"ok": False, "error": "ese torrent ya no está activo"})
    r = sources.play_torrent({}, id="GONE")
    assert r["ok"] is False and "activo" in r["error"]


# ── 4 · the two latent defects, closed before a non-YouTube row can exist ───────────────────────────────────

def test_the_blocklist_never_contains_the_empty_id():
    """`""` in this set is not one blocked video — it is a key that matches every non-YouTube row at once."""
    db = {"blocked_videos": [{"videoId": "abc"}, {"videoId": ""}, {"title": "no id at all"}]}
    assert availability.blocked_ids(db) == {"abc"}


def test_a_blocked_youtube_video_does_not_hide_the_local_items_behind_it():
    db = {"blocked_videos": [{"videoId": ""}, {"videoId": "dead"}],
          "pos": 0,
          "list": [{"videoId": "dead"},
                   {"source": "local", "videoId": "", "src": "/api/library/stream?path=video/a.mp4"}]}
    nxt = availability.next_unblocked(db, "dead")
    assert nxt is not None and nxt.get("source") == "local"


def test_swapping_to_a_local_row_finds_ITS_position_not_the_first_empty_id():
    a = {"source": "local", "videoId": "", "src": "/api/library/stream?path=video/a.mp4", "title": "A"}
    b = {"source": "local", "videoId": "", "src": "/api/library/stream?path=video/b.mp4", "title": "B"}
    db = {"list": [a, b]}
    availability.swap_to(db, b)
    assert db["pos"] == 1                       # not 0, which matching on videoId alone would have given
    assert db["source"] == "local" and db["src"].endswith("b.mp4")


def test_a_streaming_row_is_never_given_an_invented_youtube_url():
    db = {"list": []}
    availability.swap_to(db, {"source": "local", "videoId": "", "src": "/api/library/stream?path=v/a.mp4"})
    assert "youtube.com" not in db["url"]
