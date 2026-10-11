"""A video the player refused is still in his list, and the digest says so (2026-10-11, ES round, turn 7).

`build-a-video-playlist-from-links` (ES): both pasted videos came back `player_error` 150 (the owner blocks
embedding). The list digest (`ref_index` → the «items ahora» line) marked only the CURRENT row, so the refused first
video read as a plain item, and the model ended up telling him the second video «ya no está en la lista» while the
card held both. Every row on the blocklist carries «in the list, can't play here: owner blocks embedding».

Disarm: with `playability.hint` returning "" the first test goes red.
"""
from __future__ import annotations

import pytest

from widgets.youtube import data as D

RICK = {"videoId": "dQw4w9WgXcQ", "title": "Rick Astley - Never Gonna Give You Up", "channel": "Rick Astley"}
PSY = {"videoId": "9bZkp7q19f0", "title": "PSY - GANGNAM STYLE M/V", "channel": "officialpsy"}


@pytest.fixture
def both_refused(monkeypatch):
    db = {**D._seed(), "list": [RICK, PSY], "pos": 1, "videoId": PSY["videoId"], "title": PSY["title"],
          "player_error": "150", "blocked_videos": [{"videoId": RICK["videoId"]}, {"videoId": PSY["videoId"]}]}
    monkeypatch.setattr(D, "_load", lambda: dict(db))
    return db


@pytest.mark.parametrize("code, words", [("es", "en la lista, no se puede reproducir aquí"),
                                         ("en", "in the list, can't play here")])
def test_a_refused_row_that_is_not_playing_is_marked_in_the_digest(both_refused, monkeypatch, code, words):
    monkeypatch.setenv("ZAELAR_LANGUAGE", code)
    rows = D.ref_index()
    assert [r["label"] for r in rows] == [RICK["title"], PSY["title"]], "both rows are still in the list"
    assert words in rows[0]["hint"], rows[0]
    assert rows[1]["hint"], "the current refused row keeps its own mark"


def test_a_playable_row_carries_no_refusal_mark(both_refused):
    both_refused["blocked_videos"] = []
    both_refused["player_error"] = ""
    rows = D.ref_index()
    assert rows[0]["hint"] == RICK["channel"]
