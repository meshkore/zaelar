"""V2-468 · each player keeps its content in ITS OWN shape, and reading them alike invents an empty round.

`youtube` keeps a flat queue in `list`. `musica` keeps NAMED playlists in `playlists[]`, each with its own
`tracks[]`, and has no `list` key at all. `media_list` asked both of them for `list`, so every music round
was published as `n_items: 0`.

MEASURED on `play-music-and-build-playlist` (2026-08-28 21:27, ES lab, recorded). The engine did the whole
job: the model called `add_to_playlist` twice, the store finished holding `playlists=[{name: "Curro",
tracks: [the track that was playing]}]` and `yt.videoId` live with `paused: false` — both halves of the
scenario's success check. The reader published zero, and the judge wrote "hallucination of saved state, the
playlist is EMPTY", scoring result 2 and mechanism 2. Nothing in the product was wrong.

Sixth instrument-accuses-product defect of the same family, and this one is the sharpest form of it: a field
read at the wrong LEVEL does not fail loudly, it manufactures a fact — and the manufactured one reads
exactly as credible as a true one.
"""
from tests.use_cases.e2e.agent import judge, probe_client, verify

# The real payload the ES lab returned at 21:27, trimmed to the keys that carry the answer.
MUSICA_REAL = {
    "yt": {"videoId": "0iLF_rtUbq0", "title": "Música relajante para trabajar", "paused": False},
    "playlists": [{"id": "curro", "name": "Curro", "art": "",
                   "tracks": [{"title": "Música relajante para trabajar", "videoId": "0iLF_rtUbq0"}]}],
    "view": {"kind": "playlist", "id": "curro"}, "mode": "youtube",
}
YOUTUBE_REAL = {"videoId": "", "list": [{"title": "Poda del olivo"}, {"title": "Injertar un olivo"}],
                "list_name": "Olivos"}


def _read(payloads, monkeypatch):
    monkeypatch.setattr(probe_client, "widget_data", lambda w, q="": payloads.get(w))
    return verify.media_list()


def test_a_music_track_saved_in_a_named_playlist_is_counted(monkeypatch):
    """The regression itself: with the real payload, the round must not read as empty."""
    out = _read({"youtube": {"list": []}, "musica": MUSICA_REAL}, monkeypatch)
    assert out["read"] is True
    assert out["n_items"] == 1, "una canción guardada en «Curro» se leía como lista vacía"
    assert out["widgets"]["musica"]["n_named"] == 1


def test_the_playlist_NAME_travels(monkeypatch):
    """Half the errand is the name ("a list called Curro"): a track counter cannot check it."""
    out = _read({"youtube": {"list": []}, "musica": MUSICA_REAL}, monkeypatch)
    assert {"name": "Curro", "n": 1, "widget": "musica"} in out["lists"]


def test_the_flat_queue_of_the_video_player_still_reads(monkeypatch):
    """The fix must not trade one player for the other: `youtube` has no `playlists`, and never had."""
    out = _read({"youtube": YOUTUBE_REAL, "musica": {"playlists": []}}, monkeypatch)
    assert out["n_items"] == 2 and out["widgets"]["youtube"]["n_named"] == 2
    assert {"name": "Olivos", "n": 2, "widget": "youtube"} in out["lists"]


def test_both_players_add_up(monkeypatch):
    out = _read({"youtube": YOUTUBE_REAL, "musica": MUSICA_REAL}, monkeypatch)
    assert out["n_items"] == 3 and set(out["widgets"]) == {"youtube", "musica"}


def test_the_judge_is_told_which_named_lists_exist(monkeypatch):
    """The verdict this defect produced was written from the mechanism facts, so the fix has to reach them."""
    out = _read({"youtube": {"list": []}, "musica": MUSICA_REAL}, monkeypatch)
    facts = judge.mechanism_facts({"media_list": out})
    assert "LISTAS CON NOMBRE" in facts and "«Curro» (1)" in facts


def test_an_empty_player_is_still_reported_as_empty(monkeypatch):
    """The half that keeps the fix from being an amnesty: a real empty list is still the failure."""
    out = _read({"youtube": {"list": []}, "musica": {"playlists": []}}, monkeypatch)
    assert out["read"] is True and out["n_items"] == 0
    assert "VACÍA" in judge.mechanism_facts({"media_list": out})


def test_the_raw_playback_fields_are_published(monkeypatch):
    """`widgets_producing` is a CONCLUSION; the scenarios name the raw fields ("`yt.videoId` with
    `yt.paused` false"). Three rounds in a row on 2026-08-28 answered the conclusion by distrusting it —
    "the report shows no evidence the player is active" — with it stated in words right in front of them.
    A derived fact nobody can check against anything persuades nobody."""
    out = _read({"youtube": {"list": []}, "musica": MUSICA_REAL}, monkeypatch)
    pb = out["widgets"]["musica"]["playing"]
    assert pb["videoId"] == "0iLF_rtUbq0" and pb["paused"] is False and pb["loaded"] is True


def test_a_widget_with_no_playback_block_publishes_nothing(monkeypatch):
    """`youtube` keeps its playback at the top level, not under `yt` — inventing an empty block for it
    would state "nothing loaded" about a player that was never asked."""
    out = _read({"youtube": YOUTUBE_REAL, "musica": {"playlists": []}}, monkeypatch)
    assert "playing" not in out["widgets"]["youtube"]


def test_the_judge_is_shown_those_fields(monkeypatch):
    out = _read({"youtube": {"list": []}, "musica": MUSICA_REAL}, monkeypatch)
    facts = judge.mechanism_facts({"media_list": out, "widgets_producing": ["musica"]})
    assert "videoId=0iLF_rtUbq0" in facts and "paused=false" in facts
