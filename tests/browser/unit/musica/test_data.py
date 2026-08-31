"""Tests of the music connector's CARA (music widget, V2-041): view_data + apply_action."""
import pytest

from connectors.music.base import MusicResult
from connectors.spotify import auth
from widgets.musica import data as md


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    # store in tmp (do not touch the real data directory) + Spotify disconnected by default
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
    """V2-366 review: the favorites list was «Favoritos de Manolo» HARDCODED for every operator
    (leftover demo). It is now simply «Favoritos» — and in an installation that ALREADY has the old list, the
    favorite lands THERE (match by containment in _find_playlist): renaming the destination without migrating
    it would leave TWO live lineages, the trap measured in V2-242."""
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


# --- V2-384: «save it in a list called Curro» has a mechanism behind it, in ONE call ---

def test_guardar_lo_que_suena_en_una_lista_nueva_con_nombre_en_una_sola_llamada(monkeypatch):
    """The case measured live: «Done.» and nothing behind it. The model emits ONE data-op; requiring
    create_playlist + add_to_playlist was how that call resolved to nothing."""
    monkeypatch.setattr(md, "_current_track", lambda db: {"title": "La Song", "artist": "A", "album": "",
                                                          "art": "", "query": "La Song"})
    r = md.apply_action("add_to_playlist", {"playlist": "Curro"})
    assert r["ok"] is True and r["created"] is True and r["track"] == "La Song"
    db = md._load_db()
    assert [pl["name"] for pl in db["playlists"]] == ["Curro"]
    assert [t["title"] for t in db["playlists"][0]["tracks"]] == ["La Song"]
    # repeated save of the same playing track does not pile up
    r = md.apply_action("add_to_playlist", {"playlist": "Curro"})
    assert r["ok"] is True and r["created"] is False and r["count"] == 1


def test_una_lista_existente_se_reutiliza_y_un_track_explicito_gana(monkeypatch):
    monkeypatch.setattr(md, "_current_track", lambda db: None)
    md.apply_action("create_playlist", {"name": "Viaje"})
    r = md.apply_action("add_to_playlist", {"playlist": "viaje", "query": "Volare"})
    assert r["ok"] is True and r["created"] is False
    assert [t["title"] for t in md._load_db()["playlists"][0]["tracks"]] == ["Volare"]


def test_sin_cancion_y_sin_nada_sonando_no_se_crea_basura(monkeypatch):
    monkeypatch.setattr(md, "_current_track", lambda db: None)
    r = md.apply_action("add_to_playlist", {"playlist": "Curro"})
    assert r["ok"] is False and r["error"] == "nothing_playing"
    assert md._load_db()["playlists"] == []              # a failed save must not leave an empty list behind


def test_favorite_current_acepta_lista_con_nombre(monkeypatch):
    monkeypatch.setattr(md, "_current_track", lambda db: {"title": "Song", "artist": "A", "album": "",
                                                          "art": "", "query": "Song"})
    r = md.apply_action("favorite_current", {"playlist": "Curro"})
    assert r["ok"] is True
    db = md._load_db()
    assert [pl["name"] for pl in db["playlists"]] == ["Curro"]


def test_la_evidencia_del_plato_guardar_lo_que_suena_por_el_bloque_yt_nunca_deja_la_lista_vacia():
    """Harness evidence (2026-08-27 13:40): yt={videoId 0iLF_rtUbq0, paused:false} playing and
    playlists=[{id:curro, tracks:[]}] — with the claim that «favorite_current creates the list BEFORE resolving
    the track». The code says otherwise: _current_track is resolved and gates (nothing_playing) before
    _find_or_create_playlist, in BOTH branches. This test follows the REAL path (the track comes from the
    persisted yt block, without monkeypatch): if either branch started creating before resolving, the list would
    be empty and this would fail. The measured empty list is produced by `create_playlist` alone — legitimately —
    with the subsequent add lost because of the channel's one-data-op-per-turn behavior (V2-391, already fixed by
    the harness)."""
    import widgets.store as store
    store.save("musica", {"yt": {"videoId": "0iLF_rtUbq0", "title": "La que suena", "paused": False,
                                 "muted": False, "volume": 70, "cmd_seq": 3}})
    r = md.apply_action("add_to_playlist", {"playlist": "Curro"})
    assert r["ok"] is True and r["created"] is True
    db = md._load_db()
    curro = next(pl for pl in db["playlists"] if pl["name"] == "Curro")
    assert [t["title"] for t in curro["tracks"]] == ["La que suena"]      # NEVER empty

    store.save("musica", {"yt": {"videoId": "0iLF_rtUbq0", "title": "La que suena", "paused": False,
                                 "muted": False, "volume": 70, "cmd_seq": 3}})
    r = md.apply_action("favorite_current", {"playlist": "Curro2"})
    assert r["ok"] is True
    db = md._load_db()
    curro2 = next(pl for pl in db["playlists"] if pl["name"] == "Curro2")
    assert [t["title"] for t in curro2["tracks"]] == ["La que suena"]


def test_create_playlist_con_algo_sonando_ENSEÑA_el_siguiente_paso(monkeypatch):
    """Measured: «save what is playing in a Curro list» ends at create_playlist alone → EMPTY list.
    The model reads the tool result and the channel chains data-ops (V2-391): the response includes the
    next step when something is playing — and does NOT include it in silence, when the empty list is the entire request."""
    monkeypatch.setattr(md, "_current_track", lambda db: {"title": "Song", "artist": "", "album": "",
                                                          "art": "", "query": "Song"})
    r = md.apply_action("create_playlist", {"name": "Curro"})
    assert r["ok"] is True and r["empty"] is True and "add_to_playlist" in r.get("hint", "")
    monkeypatch.setattr(md, "_current_track", lambda db: None)
    r = md.apply_action("create_playlist", {"name": "Vacia"})
    assert r["ok"] is True and "hint" not in r
