"""Tests del proveedor YouTube-audio (V2-041): fallback gratis en el navegador. Store y resolución mockeados."""
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
    # V2-047 F4: play arranca; queue apila (no interrumpe); ended avanza a la siguiente; cola vacía = empty_queue.
    monkeypatch.setattr(ya, "_resolve", lambda q: ("V" + q[:10].ljust(10, "0"), q.title()))
    p = ya.YouTubeAudioProvider()
    p.play(query="beatles")
    assert p.enqueue(query="shakira").extra["queue_len"] == 1
    assert p.enqueue(query="bruce").extra["queue_len"] == 2
    assert _store["yt"]["videoId"].startswith("Vbeatles")      # sigue sonando Beatles, no lo pisó
    r = p.on_ended()
    assert r.action == "ended" and _store["yt"]["videoId"].startswith("Vshakira") and r.extra["queue_len"] == 1
    r = p.on_ended()
    assert _store["yt"]["videoId"].startswith("Vbruce") and r.extra["queue_len"] == 0
    assert p.on_ended().reason == "empty_queue"


def test_enqueue_with_nothing_playing_plays(_store, monkeypatch):
    # encolar sin nada sonando = reproducir (encolar mudo sería inútil)
    monkeypatch.setattr(ya, "_resolve", lambda q: ("VID00000001", "x"))
    r = ya.YouTubeAudioProvider().enqueue(query="x")
    assert r.ok and r.action == "play" and _store["yt"]["videoId"] == "VID00000001"


def test_no_restart_same_query_playing(_store, monkeypatch):
    # V2-047 F5: re-play de la MISMA query que ya suena → no-op (no re-resuelve, no recarga → no corta la canción).
    calls = {"n": 0}

    def _res(q):
        calls["n"] += 1
        return ("VID00000001", "Dai Dai")
    monkeypatch.setattr(ya, "_resolve", _res)
    p = ya.YouTubeAudioProvider()
    p.play(query="shakira")
    seq0 = _store["yt"]["cmd_seq"]
    r = p.play(query="shakira")                    # misma query, sonando
    assert r.ok and r.extra.get("noop") is True
    assert _store["yt"]["cmd_seq"] == seq0         # NO recargó el iframe (mismo cmd_seq)
    assert calls["n"] == 1                         # NO re-resolvió
    r2 = p.play(query="otra de shakira")           # query distinta → sí reproduce nueva
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
    # Spotify conectado → gana; si no, cae al fallback youtube (siempre disponible).
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
