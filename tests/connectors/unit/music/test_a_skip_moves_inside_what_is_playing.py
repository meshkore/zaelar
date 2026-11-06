"""«Next» moves inside what is playing, and says what it did (V2-795).

Measured live: a forty-song list built on the card played on Spotify; «pon la siguiente» ran, reported ok, and the
same song kept playing. The card started the FIRST track alone and «queued» the rest through an `enqueue` the
Spotify provider never had (the contract's default answered `unsupported`, unread) — so Spotify's playback context
was one track with nothing after it. Now a provider whose skip lives inside its context declares
`plays_lists_as_context` and receives the whole list in ONE play; a skip is checked against the song the player
reports afterwards. The Spotify Web API is faked; nothing reaches the network.
"""
from __future__ import annotations

import importlib

import pytest

from connectors.spotify import client

provider = importlib.import_module("connectors.spotify.provider")


class _Player:
    """A fake Spotify player: a context of uris and a cursor."""

    def __init__(self):
        self.context, self.pos, self.queued, self.stuck = [], 0, [], False

    def play(self, uris=None, context_uri="", device_id=""):
        self.context, self.pos = list(uris or []), 0
        return {}

    def next_track(self, device_id=""):
        if not self.stuck and self.pos + 1 < len(self.context):
            self.pos += 1
        return {}

    def previous_track(self, device_id=""):
        if self.pos > 0:
            self.pos -= 1
        return {}

    def playback_state(self):
        if not self.context:
            return {}
        uri = self.context[self.pos]
        return {"is_playing": True, "item": {"id": uri.rsplit(":", 1)[-1], "uri": uri, "name": "Song " + uri[-1],
                                             "artists": [{"name": "A"}]}}

    def add_to_queue(self, uri, device_id=""):
        self.queued.append(uri)
        return {}


@pytest.fixture
def player(monkeypatch):
    p = _Player()
    for name in ("play", "next_track", "previous_track", "playback_state", "add_to_queue"):
        monkeypatch.setattr(client, name, getattr(p, name))
    monkeypatch.setattr(client, "search", lambda q, types="track", limit=5: {"tracks": {"items": [
        {"id": "z", "uri": "spotify:track:z", "name": q, "artists": [{"name": "A"}]}]}})
    monkeypatch.setattr(provider, "_SETTLE_S", 0)
    return p


def test_a_list_is_handed_over_as_one_context(player):
    items = [("one", "spotify:track:1"), ("two", "spotify:track:2"), ("no uri yet", ""), ("three", "spotify:track:3")]
    r = provider.SpotifyProvider().play_list(items)
    assert r.ok and player.context == ["spotify:track:1", "spotify:track:2", "spotify:track:z", "spotify:track:3"]
    assert r.extra["in_context"] == 4 and r.extra["left_out"] == 0


def test_next_inside_the_context_names_the_new_song(player):
    sp = provider.SpotifyProvider()
    sp.play_list([("one", "spotify:track:1"), ("two", "spotify:track:2")])
    r = sp.next()
    assert r.ok and r.track.uri == "spotify:track:2" and "Song 2" in r.message


def test_a_skip_that_changed_nothing_says_so(player):
    sp = provider.SpotifyProvider()
    sp.play_list([("one", "spotify:track:1")])
    r = sp.next()
    assert not r.ok and r.reason == "no_next" and r.message, "an ok over the same song is the bug, said plainly"


def test_queueing_on_spotify_reaches_its_queue(player):
    sp = provider.SpotifyProvider()
    assert sp.enqueue(query="", uri="spotify:track:9").ok and player.queued == ["spotify:track:9"]
    assert sp.enqueue(query="by words").ok and player.queued[-1] == "spotify:track:z"
