"""A VIEW action passes its selector to the widget when nothing is indexed under that key (node 2.403).

V2-834 T06, use case `play-music-and-build-playlist` (sandbox, 2026-11-02): «ábreme el widget de música y enséñame la
lista Curro» → `musica:open_view {kind: playlist}` with item «Curro» → «No tengo claro a cuál te refieres». The list
existed: the music card publishes it under `playlist` (the key `add_to_playlist`/`play_playlist` take), while
`open_view` names it with `id` — a key that only LOOKS like an indexed selector (the «ends in id» convention). Nothing
was indexed under `id`, so every named `open_view` came back `no_match` and turned into a question. The widget finds
the playlist by name itself (`_find_playlist`).

Mechanism pinned here: an action declared `"view": true`, with no rows published for its key, takes the name as given
and lets the widget decide; a mutating action keeps asking, and a view with nothing named is left alone.
"""
from __future__ import annotations

import pytest

from widgets import refs, runtime

MANIFEST = {"actions": {
    "open_view": {"payload": {"kind": "now|playlist", "id": "id de la lista"}, "view": True},
    "remove_playlist": {"payload": {"playlistId": "id de la lista"}},
}}
INDEX = [{"id": "curro", "label": "Curro", "field": "playlist", "hint": "1 song"}]


@pytest.fixture
def card(monkeypatch):
    monkeypatch.setattr(runtime, "get", lambda wid: MANIFEST if wid == "musica" else None)
    monkeypatch.setattr(refs, "_ref_index", lambda wid: list(INDEX))
    monkeypatch.setattr(refs, "_exposes_ref_index", lambda wid: True)


@pytest.mark.parametrize("ref, said", [
    ("Curro", "No me cuentes, ábreme el widget de música y enséñame la lista Curro con la canción dentro."),
    ("Workout", "Just open the music widget and show me the Workout playlist."),
])
def test_a_named_view_reaches_the_widget(card, ref, said):
    got = refs.resolve("musica", "open_view", ref, {"kind": "playlist"}, order=said)
    assert got.ok and got.payload["id"] == ref, got


def test_a_mutating_action_still_asks(card):
    got = refs.resolve("musica", "remove_playlist", "Curro", {}, order="borra la lista Curro")
    assert not got.ok, got


def test_a_view_with_nothing_named_is_left_alone(card):
    got = refs.resolve("musica", "open_view", "", {"kind": "now"}, order="enséñame lo que suena")
    assert "id" not in (got.payload or {}) or not got.payload.get("id")
