"""«Put some music» names no track: the request ends with the player SOUNDING, so something is chosen — what was
sounding, then the track he played last — and only with nothing to choose from does it ask; a search for "" is never
sent (node 2.915).

Live, 2026-10-28 15:59 (T65): `play` with an empty query reached the connector as a search for "" and the reply was
«I couldn't find ""». The model's own guidance now says to choose (his tastes if known, else something varied) and
say what it chose; this is the door's half, for the turn where it still hands an empty query over.

Disarm: with `something_to_play` sending the empty query through, the first test goes red.
"""
from __future__ import annotations

import asyncio

import pytest

from connectors import music
from connectors.music.base import MusicResult
from nucleo import rails
from nucleo.flash import music_flow


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def control(action, query="", uri="", percent=0, prefer="", **_k):
        seen.append((action, query))
        return MusicResult(ok=True, action=action, provider="test")
    monkeypatch.setattr(music, "control", control)
    monkeypatch.setattr(music_flow, "_on_success", lambda *_a, **_k: None)
    return seen


def test_with_music_paused_it_resumes_and_never_searches_for_nothing(calls, monkeypatch):
    monkeypatch.setattr(rails, "get", lambda kind: {"label": "x"} if kind == "music.playing" else None)
    res = asyncio.run(music_flow.run("play", "", extract=None))
    assert res.ok and calls == [("resume", "")]


def test_a_named_track_still_goes_straight_to_the_provider(calls, monkeypatch):
    monkeypatch.setattr(rails, "get", lambda kind: None)
    res = asyncio.run(music_flow.run("play", "Bohemian Rhapsody", extract=None))
    assert res.ok and calls == [("play", "Bohemian Rhapsody")]
