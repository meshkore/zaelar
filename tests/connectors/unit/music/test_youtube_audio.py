"""Tests for the YouTube-audio provider (V2-041): free browser fallback. Store and resolution are mocked."""
import pytest

import connectors.music.youtube_audio as ya
from connectors.music import registry


@pytest.fixture
def _store(monkeypatch):
    db = {}
    monkeypatch.setattr(ya, "_load_yt", lambda: dict(db.get("yt") or {}))

    def _save(yt):
        db["yt"] = dict(yt)
    monkeypatch.setattr(ya, "_save_yt", _save)
    return db


def test_always_connected():
    assert ya.YouTubeAudioProvider().connected() is True


def test_play_resolves_and_writes_store(_store, monkeypatch):
    monkeypatch.setattr(ya, "_resolve", lambda q: ("VID00000001", "Fly Me to the Moon"))
    p = ya.YouTubeAudioProvider()
    r = p.play(query="frank sinatra")
    assert r.ok and r.extra["surface"] == "widget" and r.extra["widget"] == "musica"
    assert r.extra["videoId"] == "VID00000001"
    assert _store["yt"]["videoId"] == "VID00000001" and _store["yt"]["paused"] is False


def test_play_no_track(_store, monkeypatch):
    monkeypatch.setattr(ya, "_resolve", lambda q: ("", ""))
    r = ya.YouTubeAudioProvider().play(query="zzz")
    assert r.ok is False and r.reason == "no_track"


def test_queue_and_ended_advances(_store, monkeypatch):
    # V2-047 F4: play starts playback; queue stacks items (without interrupting); ended advances to the next item; an empty queue = empty_queue.
    monkeypatch.setattr(ya, "_resolve", lambda q: ("V" + q[:10].ljust(10, "0"), q.title()))
    p = ya.YouTubeAudioProvider()
    p.play(query="beatles")
    assert p.enqueue(query="shakira").extra["queue_len"] == 1
    assert p.enqueue(query="bruce").extra["queue_len"] == 2
    assert _store["yt"]["videoId"].startswith("Vbeatles")      # Beatles is still playing; it was not replaced
    r = p.on_ended()
    assert r.action == "ended" and _store["yt"]["videoId"].startswith("Vshakira") and r.extra["queue_len"] == 1
    r = p.on_ended()
    assert _store["yt"]["videoId"].startswith("Vbruce") and r.extra["queue_len"] == 0
    assert p.on_ended().reason == "empty_queue"


def test_enqueue_with_nothing_playing_plays(_store, monkeypatch):
    # Enqueuing when nothing is playing = play immediately (silently enqueuing it would be useless)
    monkeypatch.setattr(ya, "_resolve", lambda q: ("VID00000001", "x"))
    r = ya.YouTubeAudioProvider().enqueue(query="x")
    assert r.ok and r.action == "play" and _store["yt"]["videoId"] == "VID00000001"


def test_no_restart_same_query_playing(_store, monkeypatch):
    # V2-047 F5: replaying the SAME query that is already playing → no-op (does not resolve again or reload → does not interrupt the song).
    calls = {"n": 0}

    def _res(q):
        calls["n"] += 1
        return ("VID00000001", "Dai Dai")
    monkeypatch.setattr(ya, "_resolve", _res)
    p = ya.YouTubeAudioProvider()
    p.play(query="shakira")
    seq0 = _store["yt"]["cmd_seq"]
    r = p.play(query="shakira")                    # same query, already playing
    assert r.ok and r.extra.get("noop") is True
    assert _store["yt"]["cmd_seq"] == seq0         # Did NOT reload the iframe (same cmd_seq)
    assert calls["n"] == 1                         # Did NOT resolve again
    r2 = p.play(query="otra de shakira")           # different query → plays the new one
    assert r2.extra.get("noop") is not True and calls["n"] == 2


def test_pause_resume_volume_bump_seq(_store, monkeypatch):
    monkeypatch.setattr(ya, "_resolve", lambda q: ("VID00000001", "x"))
    p = ya.YouTubeAudioProvider()
    p.play(query="x")
    s0 = _store["yt"]["cmd_seq"]
    p.pause()
    assert _store["yt"]["paused"] is True and _store["yt"]["cmd_seq"] == s0 + 1
    p.set_volume(30)
    assert _store["yt"]["volume"] == 30


def test_next_previous_unsupported(_store, monkeypatch):
    monkeypatch.setattr(ya, "_resolve", lambda q: ("VID00000001", "x"))
    p = ya.YouTubeAudioProvider()
    p.play(query="x")
    assert p.next().reason == "unsupported" and p.previous().reason == "unsupported"


def test_extract_id_from_uri():
    assert ya._extract_id("yt:ABCDEFGHIJK") == "ABCDEFGHIJK"
    assert ya._extract_id("https://www.youtube.com/watch?v=ABCDEFGHIJK") == "ABCDEFGHIJK"


def test_registry_prefers_spotify_when_connected(monkeypatch):
    # Connected Spotify wins; otherwise, it falls back to YouTube (always available).
    registry._PROVIDERS.clear()
    registry._loaded = False
    from connectors.spotify.provider import SpotifyProvider
    names = {p.name for p in registry.providers()}
    assert {"spotify", "youtube"} <= names
    monkeypatch.setattr(SpotifyProvider, "connected", lambda self: False)
    assert registry.active().name == "youtube"
    monkeypatch.setattr(SpotifyProvider, "connected", lambda self: True)
    assert registry.active().name == "spotify"
    registry._PROVIDERS.clear(); registry._loaded = False


# --- V2-629: free cover art the instant a videoId resolves, no extra network call ---

def test_yt_thumb_derives_a_url_from_the_id_alone():
    assert ya._yt_thumb("dQw4w9WgXcQ") == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
    assert ya._yt_thumb("") == ""
    assert ya._yt_thumb(None) == ""


def test_play_writes_art_into_the_store_and_the_result_track(_store, monkeypatch):
    monkeypatch.setattr(ya, "_resolve", lambda q: ("VID00000001", "Fly Me to the Moon"))
    r = ya.YouTubeAudioProvider().play(query="frank sinatra")
    assert r.track.art == "https://i.ytimg.com/vi/VID00000001/hqdefault.jpg"
    assert _store["yt"]["art"] == "https://i.ytimg.com/vi/VID00000001/hqdefault.jpg"


def test_the_no_restart_reply_still_carries_art(_store, monkeypatch):
    """The V2-047 F5 guard returns EARLY, before any new resolution — the art must come from the STORE, not
    from re-deriving it, since a legacy stored `yt` block (written before V2-629) may have none."""
    monkeypatch.setattr(ya, "_resolve", lambda q: ("VID00000001", "Fly Me to the Moon"))
    p = ya.YouTubeAudioProvider()
    p.play(query="sinatra")
    r = p.play(query="sinatra")   # identical query, already playing -> the no-restart branch
    assert r.extra.get("noop") is True
    assert r.track.art == "https://i.ytimg.com/vi/VID00000001/hqdefault.jpg"


def test_on_ended_carries_art_for_the_next_track(_store, monkeypatch):
    monkeypatch.setattr(ya, "_resolve", lambda q: ("V" + q[:10].ljust(10, "0"), q.title()))
    p = ya.YouTubeAudioProvider()
    p.play(query="beatles")
    p.enqueue(query="shakira")
    r = p.on_ended()
    assert r.track.art == _store["yt"]["art"] == "https://i.ytimg.com/vi/Vshakira000/hqdefault.jpg"
