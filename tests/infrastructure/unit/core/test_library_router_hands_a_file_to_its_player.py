"""nucleo/library_router.py (V2-658) — the orchestration seam the archivos widget hands a local file through,
so its own `data.py` never imports `widgets.youtube`/`widgets.musica` directly (`widgets/AGENTS.md`'s
isolation rule). Sibling of `nucleo/torrent_router.py`, same shape, same reason to exist.
"""
from __future__ import annotations


def test_route_video_hands_the_path_to_the_player_shows_it_and_pauses_music(monkeypatch):
    from nucleo import library_router
    calls = []
    monkeypatch.setattr("widgets.youtube.data.apply_action",
                        lambda action, p: calls.append((action, p)) or {"ok": True})
    monkeypatch.setattr("widgets.musica.data.apply_action",
                        lambda action, p: calls.append((action, p)) or {"ok": True})
    shown = []
    monkeypatch.setattr("voice.observer.emit", lambda kind, label, **k: shown.append(k.get("extra")))
    out = library_router.route_video("video/pelicula.mp4", "La Película")
    assert out["ok"]
    assert calls[0] == ("play_local", {"path": "video/pelicula.mp4", "title": "La Película"})
    assert calls[1] == ("pause", {})                        # the other exclusive-audio surface yields
    assert shown and shown[0]["id"] == "youtube"
    assert shown[0]["src"] != "user", (
        '`src` must never be "user" — sse.js discards a show event with that src as its own echo, '
        "so the card this call exists to raise would never open (V2-658)")


def test_route_video_never_shows_or_pauses_on_a_refusal(monkeypatch):
    from nucleo import library_router
    monkeypatch.setattr("widgets.youtube.data.apply_action",
                        lambda action, p: {"ok": False, "error": "no encuentro ese vídeo"})
    calls = []
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: calls.append(1))
    out = library_router.route_video("video/gone.mp4")
    assert out["ok"] is False and not calls


def test_route_audio_hands_the_path_to_music_shows_it_and_pauses_video(monkeypatch):
    from nucleo import library_router
    calls = []
    monkeypatch.setattr("widgets.musica.data.apply_action",
                        lambda action, p: calls.append((action, p)) or {"ok": True})
    monkeypatch.setattr("widgets.youtube.data.apply_action",
                        lambda action, p: calls.append((action, p)) or {"ok": True})
    shown = []
    monkeypatch.setattr("voice.observer.emit", lambda kind, label, **k: shown.append(k.get("extra")))
    out = library_router.route_audio("audio/cancion.mp3", "Canción")
    assert out["ok"]
    assert calls[0] == ("play_local", {"path": "audio/cancion.mp3", "title": "Canción"})
    assert calls[1] == ("pause", {})
    assert shown and shown[0]["id"] == "musica"
    assert shown[0]["src"] != "user", (
        '`src` must never be "user" — sse.js discards a show event with that src as its own echo, '
        "so the card this call exists to raise would never open (V2-658)")


def test_route_audio_never_reaches_video_on_a_refusal(monkeypatch):
    from nucleo import library_router
    monkeypatch.setattr("widgets.musica.data.apply_action",
                        lambda action, p: {"ok": False, "error": "no encuentro ese audio"})
    hit = []
    monkeypatch.setattr("widgets.youtube.data.apply_action", lambda *a, **k: hit.append(1))
    out = library_router.route_audio("audio/gone.mp3")
    assert out["ok"] is False and not hit
