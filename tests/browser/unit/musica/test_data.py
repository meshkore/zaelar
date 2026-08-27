"""Tests de la CARA del conector de música (widget musica, V2-041): view_data + apply_action."""
import pytest

from connectors.music.base import MusicResult
from connectors.spotify import auth
from widgets.musica import data as md


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    # store en tmp (no tocar el data dir real) + spotify desconectado por defecto
    import widgets.store as store
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    monkeypatch.setattr(auth, "status", lambda: {"logged_in": False, "can_connect": True,
                                                 "own_client_id_set": False, "default_available": True,
                                                 "redirect_uri": "http://127.0.0.1:43917/api/spotify/callback"})
    yield


def test_view_data_idle_when_nothing():
    vd = md.view_data()
    assert vd["mode"] == "idle" and vd["connected"] is False and vd["can_connect"] is True


def test_view_data_youtube_mode_when_yt_present(monkeypatch):
    import widgets.store as store
    store.save("musica", {"yt": {"videoId": "VID00000001", "title": "x", "cmd_seq": 1}})
    vd = md.view_data()
    assert vd["mode"] == "youtube" and vd["yt"]["videoId"] == "VID00000001"


def test_view_data_spotify_mode_when_connected(monkeypatch):
    monkeypatch.setattr(auth, "status", lambda: {"logged_in": True, "can_connect": True})
    monkeypatch.setattr(md, "_now_playing", lambda: {"playing": True, "title": "Song", "artist": "A"})
    vd = md.view_data()
    assert vd["mode"] == "spotify" and vd["now_playing"]["title"] == "Song"


def test_connect_with_client_id_saves_and_returns_url(monkeypatch):
    saved = {}
    monkeypatch.setattr("config.credentials.set_key", lambda k, v: saved.setdefault(k, v))
    monkeypatch.setattr(auth, "begin_login", lambda: {"ok": True, "url": "https://accounts.spotify.com/authorize?x"})
    res = md.apply_action("connect", {"client_id": "MYCID"})
    assert res["ok"] and res["url"].startswith("https://accounts.spotify.com")
    assert saved["SPOTIFY_CLIENT_ID"] == "MYCID"


def test_connect_without_client_id_flags_need(monkeypatch):
    monkeypatch.setattr(auth, "begin_login", lambda: {"ok": False, "error": "no_client_id"})
    res = md.apply_action("connect", {})
    assert res["ok"] is False and res.get("need_client_id") is True


def test_control_routes_to_music_facade(monkeypatch):
    calls = {}

    def _fake(action, query="", percent=0, **k):
        calls["a"] = action
        return MusicResult(ok=True, action=action, message="ok")
    monkeypatch.setattr("connectors.music.control", _fake)
    res = md.apply_action("pause", {})
    assert res["ok"] and calls["a"] == "pause"


def test_unknown_action():
    assert md.apply_action("frobnicate", {})["ok"] is False


def test_favorite_current_no_lleva_nombre_de_demo_y_no_abre_un_segundo_linaje(monkeypatch):
    """V2-366 repaso: la lista de favoritos era «Favoritos de Manolo» HARDCODEADO para cualquier operador
    (resto de demo). Ahora es «Favoritos» a secas — y en una instalación que YA tiene la lista vieja, el
    favorito cae AHÍ (match por contención de _find_playlist): renombrar el destino sin migrar dejaría DOS
    linajes vivos, la trampa medida en V2-242."""
    monkeypatch.setattr(md, "_current_track", lambda db: {"title": "Song", "artist": "A", "album": "",
                                                          "art": "", "query": "Song"})
    r = md.apply_action("favorite_current", {})
    assert r["ok"] is True
    db = md._load_db()
    assert [pl["name"] for pl in db["playlists"]] == ["Favoritos"]

    # installation that already carries the old demo-named list: NO second favorites list appears
    import widgets.store as store
    store.save("musica", {"playlists": [{"id": "favoritos-de-manolo", "name": "Favoritos de Manolo",
                                         "art": "", "tracks": []}]})
    r = md.apply_action("favorite_current", {})
    assert r["ok"] is True and r["playlist"] == "favoritos-de-manolo"
    names = [pl["name"] for pl in md._load_db()["playlists"]]
    assert names == ["Favoritos de Manolo"]
