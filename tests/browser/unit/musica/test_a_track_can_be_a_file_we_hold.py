"""A track can be a FILE in the agent's own library (V2-638) — the music widget's third source.

The widget had two ways to make sound, and both are somebody else's catalog: a Spotify device, or a hidden
YouTube iframe. This is the third, and it is what makes a playlist able to mix a Spotify link, a YouTube link
and a local file, which is what the operator asked for.

The design claim these cases defend: **a local track needs no new schema.** The track shape already carries
`uri` and YouTube-audio already uses a scheme there (`yt:<id>`), so a local track is just `uri = "local:<rel>"`
and every existing path — playlists, Recent, Top, dedup — keeps working untouched.
"""
from __future__ import annotations

import pytest

from widgets.musica import local_audio


@pytest.fixture
def lib(monkeypatch, tmp_path):
    """A real library rooted in a temp workspace, and an isolated widget store."""
    from library import paths
    from nucleo import workspace as ws
    from widgets import store
    monkeypatch.setattr(ws, "root", lambda: tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path / "_wdata"))
    store._last_hash.clear()
    paths._ov_cache.update(path=None, mtime=None, data={})
    paths.ensure()
    yield paths
    paths._ov_cache.update(path=None, mtime=None, data={})


# ── the uri scheme carries it, so nothing else changes ──────────────────────────────────────────────────────

def test_a_local_track_is_recognised_by_its_uri_scheme():
    assert local_audio.is_local({"uri": "local:audio/song.mp3"}) is True
    assert local_audio.rel_of({"uri": "local:audio/song.mp3"}) == "audio/song.mp3"
    for other in ({"uri": "yt:abc"}, {"uri": "spotify:track:x"}, {}, {"uri": ""}):
        assert local_audio.is_local(other) is False
        assert local_audio.rel_of(other) == ""


def test_a_file_becomes_a_track_with_the_ordinary_shape(lib):
    (lib.dir_for("audio") / "Miles Davis - So What.mp3").write_bytes(b"x")
    t = local_audio.track_from_library("audio/Miles Davis - So What.mp3")
    assert t["artist"] == "Miles Davis" and t["title"] == "So What"
    assert t["uri"] == "local:audio/Miles Davis - So What.mp3"
    assert t["src"].startswith("/api/library/stream?path=")
    assert set(("title", "artist", "album", "art", "query", "uri", "videoId")) <= set(t)


def test_a_filename_without_a_delimiter_never_invents_an_artist(lib):
    """Guessing an artist from a bare filename is how a library fills with wrong credits that then propagate
    into Recent, Top and every playlist that holds the track."""
    (lib.dir_for("audio") / "track01.mp3").write_bytes(b"x")
    t = local_audio.track_from_library("audio/track01.mp3")
    assert t["artist"] == "" and t["title"] == "track01"


def test_a_file_that_is_not_playable_audio_is_refused(lib):
    (lib.dir_for("audio") / "song.wma").write_bytes(b"x")     # audio, but no browser decodes it
    (lib.dir_for("video") / "film.mp4").write_bytes(b"x")     # playable, but not audio
    assert local_audio.track_from_library("audio/song.wma") is None
    assert local_audio.track_from_library("video/film.mp4") is None
    assert local_audio.track_from_library("audio/missing.mp3") is None


# ── playing one: the bar shows ONE thing ───────────────────────────────────────────────────────────────────

def test_playing_a_local_track_clears_the_youtube_block(lib):
    """Leaving it behind would have the card claiming two songs at once."""
    (lib.dir_for("audio") / "a.mp3").write_bytes(b"x")
    db = {"yt": {"videoId": "abc", "cmd_seq": 3}}
    r = local_audio.play(db, local_audio.track_from_library("audio/a.mp3"))
    assert r["ok"] and db["local"]["src"] and db["yt"] == {}


def test_replaying_the_same_file_is_a_new_event(lib):
    """Without a bumped seq the widget cannot tell «play this again» from «nothing changed», and the second
    request is silently ignored."""
    (lib.dir_for("audio") / "a.mp3").write_bytes(b"x")
    t = local_audio.track_from_library("audio/a.mp3")
    db = {}
    local_audio.play(db, t)
    first = db["local"]["seq"]
    local_audio.play(db, t)
    assert db["local"]["seq"] == first + 1


def test_a_file_deleted_since_it_was_listed_refuses_out_loud(lib):
    (lib.dir_for("audio") / "a.mp3").write_bytes(b"x")
    t = local_audio.track_from_library("audio/a.mp3")
    (lib.dir_for("audio") / "a.mp3").unlink()
    r = local_audio.play({}, t)
    assert r["ok"] is False and "biblioteca" in r["reason"]


# ── the widget: dispatch, the bar's mode, and mixed playlists ──────────────────────────────────────────────

def test_the_bar_reports_a_third_mode(lib):
    from widgets.musica import data
    (lib.dir_for("audio") / "a.mp3").write_bytes(b"x")
    out = data.apply_action("play_local", {"path": "audio/a.mp3"})
    assert out["ok"]
    assert data.view_data()["mode"] == "local"


def test_play_local_refuses_a_file_that_is_not_there(lib):
    from widgets.musica import data
    r = data.apply_action("play_local", {"path": "audio/nope.mp3"})
    assert r["ok"] is False and "biblioteca" in r["error"]


def test_a_played_local_track_lands_in_recent(lib):
    from widgets.musica import data
    (lib.dir_for("audio") / "Nina Simone - Feeling Good.mp3").write_bytes(b"x")
    data.apply_action("play_local", {"path": "audio/Nina Simone - Feeling Good.mp3"})
    recent = data.view_data().get("recent") or []
    assert any(t.get("title") == "Feeling Good" and t.get("artist") == "Nina Simone" for t in recent)


def test_a_connector_track_still_goes_through_the_connector(lib, monkeypatch):
    """The local branch must not swallow the ordinary path."""
    from widgets.musica import data
    seen = {}

    class _R:
        ok, message, reason, track = True, "", "", None

    monkeypatch.setattr("connectors.music.control",
                        lambda action, **k: seen.update({"action": action, **k}) or _R(), raising=False)
    r = data._play_track({"title": "Something", "query": "something", "uri": "yt:abc"}, {})
    assert r["ok"] and seen["action"] == "play" and seen["uri"] == "yt:abc"


def test_a_local_track_in_a_playlist_is_never_queued_into_the_connector(lib, monkeypatch):
    """The connector queue holds query STRINGS it re-resolves; a file has nothing to re-resolve, so queueing
    it would silently drop it."""
    from widgets.musica import data
    (lib.dir_for("audio") / "a.mp3").write_bytes(b"x")
    (lib.dir_for("audio") / "b.mp3").write_bytes(b"x")
    queued = []

    class _R:
        ok, message, reason, track = True, "", "", None

    monkeypatch.setattr("connectors.music.control",
                        lambda action, **k: (queued.append((action, k.get("uri"))) if action == "queue" else None) or _R(),
                        raising=False)
    a = local_audio.track_from_library("audio/a.mp3")
    b = local_audio.track_from_library("audio/b.mp3")
    spot = {"title": "S", "artist": "", "album": "", "art": "", "query": "s", "uri": "spotify:track:s",
            "videoId": ""}
    db = data._load_db()
    db["playlists"] = [{"id": "mix", "name": "Mix", "art": "", "tracks": [a, spot, b]}]
    data._persist(db)
    out = data.apply_action("play_playlist", {"playlist": "mix"})
    assert out["ok"]
    assert [u for _, u in queued] == ["spotify:track:s"]      # only the connector track was queued
    assert data.view_data()["mode"] == "local"                # and the local first track is what plays


def test_a_local_track_ending_clears_the_bar(lib):
    from widgets.musica import data
    (lib.dir_for("audio") / "a.mp3").write_bytes(b"x")
    data.apply_action("play_local", {"path": "audio/a.mp3"})
    assert data.view_data()["mode"] == "local"
    data.apply_action("ended", {})
    assert data.view_data()["mode"] != "local"
