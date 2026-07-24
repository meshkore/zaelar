"""Tests del SpotifyProvider (V2-041): mapeo a Track/NowPlaying + recuperación de NO_ACTIVE_DEVICE. Cliente mockeado."""
import pytest

from connectors.spotify import client as spclient
from connectors.spotify.client import SpotifyError
from connectors.spotify.provider import SpotifyProvider

_TRACK = {"id": "t1", "uri": "spotify:track:t1", "name": "Fly Me to the Moon",
          "artists": [{"name": "Frank Sinatra"}], "album": {"name": "Sinatra", "images": [{"url": "http://art"}]},
          "duration_ms": 148000}


@pytest.fixture
def prov(monkeypatch):
    monkeypatch.setattr(SpotifyProvider, "connected", lambda self: True)
    return SpotifyProvider()


def test_search_maps_tracks(prov, monkeypatch):
    monkeypatch.setattr(spclient, "search", lambda q, types="track", limit=5: {"tracks": {"items": [_TRACK]}})
    hits = prov.search("frank sinatra")
    assert hits and hits[0].title == "Fly Me to the Moon" and hits[0].artist == "Frank Sinatra"
    assert hits[0].label() == "Fly Me to the Moon — Frank Sinatra"


def test_play_query_searches_then_plays(prov, monkeypatch):
    calls = {}
    monkeypatch.setattr(spclient, "search", lambda q, types="track", limit=5: {"tracks": {"items": [_TRACK]}})
    monkeypatch.setattr(spclient, "play", lambda uris=None, context_uri="", device_id="": calls.setdefault("uris", uris))
    r = prov.play(query="frank sinatra")
    assert r.ok and r.track.uri == "spotify:track:t1"
    assert calls["uris"] == ["spotify:track:t1"] and "Fly Me to the Moon" in r.message


def test_play_no_track_found(prov, monkeypatch):
    monkeypatch.setattr(spclient, "search", lambda q, types="track", limit=5: {"tracks": {"items": []}})
    r = prov.play(query="asdkfjhaskdfj")
    assert r.ok is False and r.reason == "no_track"


def test_no_active_device_recovers_with_device_id(prov, monkeypatch):
    monkeypatch.setattr(spclient, "search", lambda q, types="track", limit=5: {"tracks": {"items": [_TRACK]}})
    tried = []

    def _play(uris=None, context_uri="", device_id=""):
        tried.append(device_id)
        if not device_id:
            raise SpotifyError(404, "no_device", "no active device")
        return {}

    monkeypatch.setattr(spclient, "play", _play)
    monkeypatch.setattr(spclient, "devices", lambda: [{"id": "dev9", "is_active": False}])
    r = prov.play(query="frank sinatra")
    assert r.ok and tried == ["", "dev9"]          # 1º sin device (404) → 2º con el device encontrado


def test_no_device_at_all_reports_reason(prov, monkeypatch):
    monkeypatch.setattr(spclient, "search", lambda q, types="track", limit=5: {"tracks": {"items": [_TRACK]}})
    monkeypatch.setattr(spclient, "play",
                        lambda uris=None, context_uri="", device_id="": (_ for _ in ()).throw(
                            SpotifyError(404, "no_device", "x")))
    monkeypatch.setattr(spclient, "devices", lambda: [])
    r = prov.play(query="frank sinatra")
    assert r.ok is False and r.reason == "no_device" and r.message


def test_premium_error_reported(prov, monkeypatch):
    monkeypatch.setattr(spclient, "pause",
                        lambda device_id="": (_ for _ in ()).throw(SpotifyError(403, "premium", "x")))
    r = prov.pause()
    assert r.ok is False and r.reason == "premium"


def test_now_playing_parses_state(prov, monkeypatch):
    monkeypatch.setattr(spclient, "playback_state",
                        lambda: {"is_playing": True, "item": _TRACK, "device": {"name": "iPhone", "volume_percent": 40}})
    np = prov.now_playing()
    assert np.playing and np.track.title == "Fly Me to the Moon" and np.device == "iPhone" and np.volume == 40
