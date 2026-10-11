"""`next` tells «there is nothing after this one» apart from «the next one can't play here» (2026-10-11, ES turn 6).

`build-a-video-playlist-from-links` (ES): with PSY (the last row) refused by the player, «el siguiente es Gangnam
Style, pon ese» ran `next` and the card answered «No hay más vídeos en la lista.»; the reply said exactly that, and
the turn after the model believed the video had left the list. The refusal now names the row and the reason.

Disarm: with `playability.next_refusal` returning None the first two tests go red (the bare «No hay más vídeos»).
"""
from __future__ import annotations

import pytest

from widgets.youtube import data as _data  # noqa: F401 — the package loads through `data` (it imports `actions`)
from widgets.youtube import actions as A

RICK = {"videoId": "dQw4w9WgXcQ", "title": "Rick Astley - Never Gonna Give You Up"}
PSY = {"videoId": "9bZkp7q19f0", "title": "PSY - GANGNAM STYLE M/V"}
BLOCK = [{"videoId": RICK["videoId"]}, {"videoId": PSY["videoId"]}]


@pytest.fixture(autouse=True)
def spanish(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")


def test_past_the_last_row_the_player_refused_it_names_it_as_unplayable_and_still_listed():
    db = {"list": [RICK, PSY], "pos": 1, "videoId": PSY["videoId"], "player_error": "150", "blocked_videos": BLOCK}
    r = A._a_next("next", {}, db)
    assert r["ok"] is False and r["error"] == "end_after_unplayable"
    assert PSY["title"] in r["message"] and "propietario" in r["message"] and "No hay más" not in r["message"]


def test_a_next_row_the_player_refused_is_said_to_be_in_the_list_but_unplayable(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    db = {"list": [RICK, PSY], "pos": 0, "videoId": RICK["videoId"], "blocked_videos": BLOCK}
    r = A._a_next("next", {}, db)
    assert r["error"] == "next_cannot_play" and PSY["title"] in r["message"] and "still in the list" in r["message"]


def test_a_real_end_of_list_is_still_no_more_videos():
    db = {"list": [RICK, PSY], "pos": 1, "videoId": PSY["videoId"], "player_error": "", "blocked_videos": []}
    r = A._a_next("next", {}, db)
    assert r["error"] == "end_of_list"


def test_a_playable_row_further_on_keeps_the_old_path(monkeypatch):
    third = {"videoId": "ccccccccccc", "title": "Third"}
    db = {"list": [RICK, PSY, third], "pos": 0, "videoId": RICK["videoId"], "blocked_videos": BLOCK[1:]}
    played = []
    monkeypatch.setattr(A._d, "_play_pos", lambda d, i, cmd, **k: played.append(i) or {"ok": True})
    assert A._a_next("next", {}, db) == {"ok": True} and played == [1]
