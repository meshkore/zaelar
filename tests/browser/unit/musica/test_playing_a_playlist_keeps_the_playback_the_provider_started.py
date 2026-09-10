# V2-650 — playing a playlist must KEEP the playback the provider just started.
#
# Measured live (session aed0736c, 2026-09-10 08:18, the «True Blue» errand): «reproduce la lista»
# resolved the first track, the provider wrote yt.videoId plus an 8-track queue into the musica store
# through its own load/save — and play_playlist then persisted the snapshot it had loaded BEFORE the
# provider ran, erasing the playback state it had just created. Nothing sounded, the action reported
# ok, and the store held yt={} as the only evidence. The read-modify-write class is already paid
# elsewhere (V2-611): a stale snapshot is never written back over a store a collaborator writes to.
import pytest

from connectors.music.base import MusicResult
from connectors.spotify import auth
from widgets.musica import data as md


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    import widgets.store as store
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    monkeypatch.setattr(auth, "status", lambda: {"logged_in": False, "can_connect": True,
                                                 "own_client_id_set": False, "default_available": True,
                                                 "redirect_uri": "http://127.0.0.1:43917/api/spotify/callback"})
    yield


def _seed_playlist():
    import widgets.store as store
    store.save("musica", {"playlists": [{"id": "true-blue", "name": "True Blue", "tracks": [
        {"title": "Papa Don't Preach", "artist": "Madonna", "query": "Papa Don't Preach"},
        {"title": "Open Your Heart", "artist": "Madonna", "query": "Open Your Heart"},
    ]}]})


def _provider_like_control(action, query="", uri="", percent=0, **_k):
    """The REAL provider contract, miniaturized: play/queue write the yt block into the store through
    their own load/save (exactly what youtube_audio._save_yt does), invisibly to any snapshot the
    caller is still holding."""
    import widgets.store as store
    db = store.load("musica", {})
    yt = dict(db.get("yt") or {})
    if action == "play":
        yt.update({"videoId": "VID_LIVE_001", "title": query, "query": query, "paused": False})
    elif action == "queue":
        yt.setdefault("queue", []).append(query)
    db["yt"] = yt
    store.save("musica", db)
    return MusicResult(ok=True, action=action, message="Suena " + (query or "la música") + ".")


def test_play_playlist_keeps_the_yt_state_the_provider_wrote(monkeypatch):
    _seed_playlist()
    import connectors.music as music
    monkeypatch.setattr(music, "control", _provider_like_control)
    res = md.apply_action("play_playlist", {"playlist": "True Blue"})
    assert res["ok"] is True and res["playlist"] == "true-blue"
    import widgets.store as store
    db = store.load("musica", {})
    yt = db.get("yt") or {}
    assert yt.get("videoId") == "VID_LIVE_001", \
        "the stale snapshot erased the playback the provider just started — the live silence bug"
    assert yt.get("queue") == ["Open Your Heart"], \
        "the queued rest of the album must survive the final persist too"


def test_play_playlist_still_applies_its_own_view_and_recent(monkeypatch):
    """The re-load is not allowed to LOSE this action's own writes: the view lands on the playlist and
    the first track enters Recent, same as before the fix."""
    _seed_playlist()
    import connectors.music as music
    monkeypatch.setattr(music, "control", _provider_like_control)
    md.apply_action("play_playlist", {"playlist": "true-blue"})
    import widgets.store as store
    db = store.load("musica", {})
    assert db.get("view") == {"kind": "playlist", "id": "true-blue"}
    recent = db.get("recent") or []
    assert recent and recent[0].get("title") == "Papa Don't Preach"


def test_a_failed_resolution_reports_not_ok_with_the_providers_message(monkeypatch):
    """When the provider cannot resolve the first track, the action must SAY so (ok False + message),
    never a green nothing — the other half of the live silence."""
    _seed_playlist()
    import connectors.music as music
    monkeypatch.setattr(music, "control",
                        lambda action, query="", uri="", percent=0, **_k: MusicResult(
                            ok=False, action=action, reason="no_track",
                            message=f"No he encontrado «{query}»."))
    res = md.apply_action("play_playlist", {"playlist": "true-blue"})
    assert res["ok"] is False
    assert "No he encontrado" in (res.get("message") or "")


def test_a_spoken_garble_of_the_only_plausible_list_still_plays(monkeypatch):
    """«arranca la lista de Trublo» — the STT's rendering of «True Blue», measured live 2026-09-10:
    the exact/containment finder missed and the operator got a raw code over music he had just named."""
    _seed_playlist()
    import connectors.music as music
    monkeypatch.setattr(music, "control", _provider_like_control)
    res = md.apply_action("play_playlist", {"playlist": "Trublo"})
    assert res["ok"] is True and res["playlist"] == "true-blue"


def test_a_hopeless_reference_refuses_with_a_sentence_that_names_the_lists(monkeypatch):
    _seed_playlist()
    import connectors.music as music
    monkeypatch.setattr(music, "control", _provider_like_control)
    res = md.apply_action("play_playlist", {"playlist": "los cuarenta principales"})
    assert res["ok"] is False and res["error"] == "playlist_not_found"
    msg = res.get("message") or ""
    assert "True Blue" in msg, "the refusal must NAME what exists — the raw code was read aloud"
    assert "los cuarenta principales" in msg


def test_two_plausible_lists_stay_a_refusal_never_a_guess(monkeypatch):
    import widgets.store as store
    store.save("musica", {"playlists": [
        {"id": "true-blue", "name": "True Blue", "tracks": [{"title": "A", "query": "A"}]},
        {"id": "true-blues", "name": "True Blues", "tracks": [{"title": "B", "query": "B"}]},
    ]})
    import connectors.music as music
    monkeypatch.setattr(music, "control", _provider_like_control)
    res = md.apply_action("play_playlist", {"playlist": "Trublo"})
    assert res["ok"] is False, "with two near-matches, guessing plays the wrong music — refuse and name both"
    assert "True Blue" in (res.get("message") or "") and "True Blues" in (res.get("message") or "")
