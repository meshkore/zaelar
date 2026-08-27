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


# --- V2-384: «guárdamelo en una lista que se llame Curro» tiene mecanismo detrás, en UNA llamada ---

def test_guardar_lo_que_suena_en_una_lista_nueva_con_nombre_en_una_sola_llamada(monkeypatch):
    """El caso medido en vivo: «Hecho.» y nada detrás. El modelo emite UNA data-op; exigir
    create_playlist + add_to_playlist era cómo esa llamada resolvía a nada."""
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
    """Evidencia del arnés (2026-08-27 13:40): yt={videoId 0iLF_rtUbq0, paused:false} sonando y
    playlists=[{id:curro, tracks:[]}] — con la atribución «favorite_current crea la lista ANTES de resolver
    la pista». Contra el código NO es así: _current_track se resuelve y gatea (nothing_playing) antes de
    _find_or_create_playlist, en las DOS ramas. Este test recorre el camino REAL (la pista sale del bloque
    yt persistido, sin monkeypatch): si alguna rama volviera a crear antes de resolver, la lista saldría
    vacía y esto se pone rojo. La lista vacía medida la produce `create_playlist` a secas — legítimo — con
    el add de después perdido por el una-data-op-por-turno del canal (V2-391, ya arreglado por el arnés)."""
    import widgets.store as store
    store.save("musica", {"yt": {"videoId": "0iLF_rtUbq0", "title": "La que suena", "paused": False,
                                 "muted": False, "volume": 70, "cmd_seq": 3}})
    r = md.apply_action("add_to_playlist", {"playlist": "Curro"})
    assert r["ok"] is True and r["created"] is True
    db = md._load_db()
    curro = next(pl for pl in db["playlists"] if pl["name"] == "Curro")
    assert [t["title"] for t in curro["tracks"]] == ["La que suena"]      # NUNCA vacía

    store.save("musica", {"yt": {"videoId": "0iLF_rtUbq0", "title": "La que suena", "paused": False,
                                 "muted": False, "volume": 70, "cmd_seq": 3}})
    r = md.apply_action("favorite_current", {"playlist": "Curro2"})
    assert r["ok"] is True
    db = md._load_db()
    curro2 = next(pl for pl in db["playlists"] if pl["name"] == "Curro2")
    assert [t["title"] for t in curro2["tracks"]] == ["La que suena"]


def test_create_playlist_con_algo_sonando_ENSEÑA_el_siguiente_paso(monkeypatch):
    """Medido: «guárdame lo que suena en una lista Curro» acaba en create_playlist a secas → lista VACÍA.
    El modelo lee el resultado de la tool y el canal encadena data-ops (V2-391): la respuesta lleva el
    siguiente paso cuando suena algo — y NO lo lleva con silencio, donde la lista vacía es todo el encargo."""
    monkeypatch.setattr(md, "_current_track", lambda db: {"title": "Song", "artist": "", "album": "",
                                                          "art": "", "query": "Song"})
    r = md.apply_action("create_playlist", {"name": "Curro"})
    assert r["ok"] is True and r["empty"] is True and "add_to_playlist" in r.get("hint", "")
    monkeypatch.setattr(md, "_current_track", lambda db: None)
    r = md.apply_action("create_playlist", {"name": "Vacia"})
    assert r["ok"] is True and "hint" not in r
