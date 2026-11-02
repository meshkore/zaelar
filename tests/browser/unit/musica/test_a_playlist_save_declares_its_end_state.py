"""A save into a playlist declares the end state it leaves, so the turn can say it is there (node 4.335).

V2-834 T07, use case `play-music-and-build-playlist` (sandbox, 2026-11-02): «¿me lo puedes guardar en una lista que se
llame Curro?» → `musica:add_to_playlist {playlist: Curro}` ran, but the action declared no `done_when`: the verdict was
«sin condición declarada — no se afirma nada», and the next turn told him «aún no tengo confirmación de que la lista
esté creada» over a list that existed. `add_tracks` already declared the shape; its two siblings did not.
"""
from __future__ import annotations

import pytest

from widgets.musica import data as md


@pytest.mark.parametrize("action, payload", [("add_to_playlist", {"playlist": "Curro"}),
                                             ("create_playlist", {"name": "Workout"})])
def test_the_action_declares_the_playlist_it_leaves(action, payload):
    from nucleo.circuit import spec, verify
    dw = spec.render("musica", action, payload)
    assert dw and spec.target_of(dw) == "musica:playlists", dw
    assert verify.check(dw) is False, "nothing saved yet: not met"


def test_the_end_state_holds_once_the_list_exists():
    from nucleo.circuit import spec, verify
    assert md.apply_action("create_playlist", {"name": "Workout"})["ok"]
    assert verify.check(spec.render("musica", "create_playlist", {"name": "Workout"})) is True
    assert verify.check(spec.render("musica", "add_to_playlist", {"playlist": "workout"})) is True


def test_a_named_song_is_attested_in_the_list_not_just_the_list():
    """S1 audit H12: T07's end state attested that the LIST existed, so `verify` said «met» over a list that was still
    empty when the song he named never went in. When the payload names the song, the list must hold it; with no song
    named (the one playing), the list alone is what can be attested — `{title?}` drops out."""
    from nucleo.circuit import spec, verify
    assert md.apply_action("create_playlist", {"name": "Curro"})["ok"]
    named = spec.render("musica", "add_to_playlist", {"playlist": "Curro", "title": "Take On Me", "artist": "a-ha"})
    assert verify.check(named) is False, "the list exists, the song is not in it: not met"
    db = md._load_db()
    md._persist({**db, "playlists": [dict(p, tracks=[{"title": "Take On Me", "artist": "a-ha"}])
                                     if p.get("name") == "Curro" else p for p in db["playlists"]]})
    assert verify.check(named) is True
    assert verify.check(spec.render("musica", "add_to_playlist", {"playlist": "Curro"})) is True
