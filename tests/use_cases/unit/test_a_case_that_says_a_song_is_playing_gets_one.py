"""A case whose persona says «it's still playing» gets a song playing on the music card before the opening line.

`music-save-what-is-sounding` (2026-10-11): the tester said the song was still playing while the sandbox's player
was empty, so every `favorite_current` was refused with `nothing_playing` — the EN round scored 2/5 for a premise
only the tester held, and the ES round passed only for saying honestly that nothing was sounding. `card_seed` now
writes the scene through the music card's own store, and the judge is told which song was sounding.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import card_seed


def test_both_twins_declare_the_music_scene():
    for case in ("music-save-what-is-sounding__es", "music-save-what-is-sounding__us"):
        assert card_seed.card_for(case) == "musica" and card_seed.scene_for(case)["videoId"]
    assert card_seed.card_for("music-playlist-reads-clean__es") == ""
    assert card_seed.card_for("video-blocked-channel-respected") == "youtube"


def test_the_scene_lands_as_the_track_the_card_resolves(tmp_path):
    got = card_seed.sow(str(tmp_path), card_seed.scene_for("music-save-what-is-sounding"), "musica")
    assert got == {"title": "One More Time", "artist": "Daft Punk"}


def test_the_judge_is_told_which_song_was_sounding():
    note = card_seed.judge_note({"card": "musica", "seeded": True, "title": "One More Time", "artist": "Daft Punk"})
    assert "One More Time" in note and "favorite_current" in note
    assert "Rick Astley" not in note
