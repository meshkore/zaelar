"""A `play_music` that STARTED is named in the text reply, not promised (play-music-and-build-playlist__us, 2026-10-14).

«Put on some calm music for working.» → `play_music` ran, the rail had «Focus Music for Work and Studying…» playing
at 3.3 s, and the only reply, sent at 3.9 s, was «I'll put something calm on for you.» — a future-tense promise of
what had already happened, naming nothing. The persona had no way to know what was on and left. The text channel's
transport receipt now reads the music turn's own report too: a play that started owes «Now playing: «…».».

Disarm: drop the `musica` branch of `reply_receipts._holding` and the first test goes red; drop
the generic words from `_FILLER` and «some calm music» counts as naming the title (second test red).
"""
from __future__ import annotations

import pytest

from nucleo.turn import reply_receipts as RR


def _owed(said, ops, lang=None):
    out = RR.player_owed(said, ops, lang)
    return out[0].said if out else ""


async def _settled(said, ops, lang=None):
    out = await RR.player(said, ops, lang)
    return out[0].said if out else ""

TITLE = "Focus Music for Work and Studying, Background Music for Concentration, Study Music"
REPLY = "I'll put something calm on for you."
PLAYED = {"executed": "play_music", "ok": True, "accion": "play", "query": "calm music for working", "message": ""}


@pytest.fixture
def music_playing(monkeypatch):
    from widgets import store
    db = {"yt": {"videoId": "_4kHxtiuML0", "title": TITLE, "paused": False}}
    monkeypatch.setattr(store, "load", lambda wid, *a, **k: dict(db) if wid == "musica" else {})
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    return db


def test_a_play_that_started_names_what_is_on(music_playing):
    assert (REPLY + " " + _owed(REPLY, [("musica", "play")])).strip() == f"{REPLY} Now playing: «{TITLE}»."


def test_a_generic_music_word_is_not_naming_the_title(music_playing):
    out = ("Putting on some calm music for you." + " " + _owed("Putting on some calm music for you.", [("musica", "play")])).strip()
    assert out.endswith(f"Now playing: «{TITLE}».")
    assert (f"Now playing {TITLE}." + " " + _owed(f"Now playing {TITLE}.", [("musica", "play")])).strip() == f"Now playing {TITLE}."


