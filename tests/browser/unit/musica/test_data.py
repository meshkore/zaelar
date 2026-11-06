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


def test_connect_is_not_an_action_of_the_card_any_more():
    """Spotify is linked in the ⚙ Conectores section since 2026-10-04 (the one door, with the own-app client id
    field moved there); the card answers an unknown action, never a consent URL."""
    res = md.apply_action("connect", {"client_id": "MYCID"})
    assert res["ok"] is False and res["error"] == "unknown_action"


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


# --- V2-384: «save it in a list called Curro» has a mechanism behind it, in ONE call ---

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


# --- V2-XXX (pro redesign): an explicit delimiter splits a combined "Artist - Title" search string ---

# ── V2-717 · moving the playhead ─────────────────────────────────────────────────────────────────────────
# The operator asked for a progress bar he can DRAG, and — the house rule since the contacts batch — a control
# on the card must also have a spoken door. The tricky half is that for two of the three sources the server
# has no playhead at all: the sound is made inside his page.

def test_a_voice_seek_on_the_free_source_becomes_a_numbered_command_not_a_position():
    """YouTube-audio plays in the page. The server cannot move that playhead, so it leaves an INTENTION —
    and the counter is its own, never `cmd_seq`: a seek that rode the shared sequence would re-apply itself
    on the next pause or volume command, which is a song that jumps backwards when you touch the volume."""
    import widgets.store as store
    store.save("musica", {"yt": {"videoId": "VID00000001", "title": "x", "cmd_seq": 4}})
    assert md.apply_action("seek", {"to": 125})["ok"] is True
    yt = md._load_db()["yt"]
    assert yt["seek"] == {"n": 1, "to": 125.0}
    assert yt["cmd_seq"] == 5, "the widget still has to notice the command arrived"

    assert md.apply_action("seek", {"by": -10})["ok"] is True
    yt = md._load_db()["yt"]
    assert yt["seek"] == {"n": 2, "by": -10.0}, "a relative move says BY, and the counter advances"
    assert "to" not in yt["seek"], "an absolute position left behind would win over the relative ask"


def test_a_seek_with_nothing_playing_is_a_refusal_not_a_silent_ok():
    r = md.apply_action("seek", {"to": 30})
    assert r["ok"] is False and r.get("reason") == "no_track"


def test_a_seek_on_a_file_we_hold_never_restarts_the_file():
    """`seq` means «start this file again» (V2-638). A seek that bumped it would restart the very song it
    was asked to move inside — measured as the design of the local player, not guessed."""
    import widgets.store as store
    store.save("musica", {"local": {"src": "/api/library/audio/x.mp3", "rel": "audio/x.mp3",
                                    "title": "X", "paused": False, "seq": 3}})
    assert md.apply_action("seek", {"to": 42})["ok"] is True
    loc = md._load_db()["local"]
    assert loc["seek"] == {"n": 1, "to": 42.0} and loc["seq"] == 3
    assert md.view_data()["local"]["seek"] == {"n": 1, "to": 42.0}, "the command has to reach the page"


def test_a_seek_with_no_number_at_all_nudges_forward_instead_of_failing():
    """«adelanta» with no amount is a real sentence. Thirty seconds forward is an answer; an error is not."""
    import widgets.store as store
    store.save("musica", {"yt": {"videoId": "VID00000001", "title": "x", "cmd_seq": 1}})
    assert md.apply_action("seek", {})["ok"] is True
    assert md._load_db()["yt"]["seek"] == {"n": 1, "by": 30.0}


def test_the_card_is_told_where_the_spotify_song_is_and_how_long_it_lasts(monkeypatch):
    """Spotify plays on a device that is not here, so the card cannot read a clock: it needs the photograph
    (`progress_ms`) AND the length, or it draws no bar at all rather than one pinned at zero."""
    from connectors.music.base import NowPlaying, Track
    monkeypatch.setattr(auth, "status", lambda: {"logged_in": True, "can_connect": True})
    np = NowPlaying(playing=True, device="Salón", volume=40, provider="spotify", progress_ms=61000,
                    track=Track(title="Song", artist="A", album="Alb", duration_ms=214000))
    monkeypatch.setattr("connectors.music.now_playing", lambda *a, **k: np)
    vd = md.view_data()
    assert vd["now_playing"]["progress_ms"] == 61000
    assert vd["now_playing"]["duration_ms"] == 214000


def test_the_song_screen_is_reachable_by_voice_under_the_name_it_was_born_with():
    """`nowplaying` was declared in V2-058 and never implemented; a model that learned it — or an old
    data-op — must land on the screen it was always asking for rather than silently on the library."""
    assert md.apply_action("open_view", {"kind": "nowplaying"})["view"]["kind"] == "now"
    assert md.apply_action("open_view", {"kind": "library"})["view"]["kind"] == "library"
    assert md.apply_action("open_view", {"kind": "connect"})["view"]["kind"] == "connect"
    assert md.apply_action("open_view", {"kind": "podcast"})["view"]["kind"] == "home", "unknown → the adaptive one"


def test_a_seek_never_follows_the_song_it_was_asked_of():
    """A new video is loaded IN PLACE in the same block, so an unapplied seek would cross over and move the
    next song by the seconds meant for the last one."""
    import widgets.store as store
    store.save("musica", {"yt": {"videoId": "VID00000001", "title": "x", "cmd_seq": 1}})
    md.apply_action("seek", {"to": 90})
    assert md._load_db()["yt"]["seek"]["to"] == 90.0
    from connectors.music import youtube_audio as ya
    yt = ya._load_yt()
    yt["videoId"] = "VID00000002"
    ya._bump(yt, "load")
    assert "seek" not in md._load_db()["yt"], "the next song starts where it starts"


def test_the_cards_own_your_music_page_is_a_face_that_stays():
    # The responsive pass: «Your music» is a face of its own (its id = the open tab), not a fall-back to home.
    r = md.apply_action("open_view", {"kind": "collection", "id": "favorites"})
    assert r["ok"] and r["view"] == {"kind": "collection", "id": "favorites"}
    assert md.view_data()["view"] == {"kind": "collection", "id": "favorites"}
