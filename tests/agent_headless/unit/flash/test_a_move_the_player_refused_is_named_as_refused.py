"""A next/play the embedded player REFUSED is never receipted as «now playing» (2026-10-11, ES round, turn 5).

`build-a-video-playlist-from-links` (ES): «Pasa al siguiente» → `youtube:next` returned ok with Rick Astley loaded, the
transport receipt read the card at that instant and appended «Suena ahora «Rick Astley…»», and 1.0 s / 1.6 s later
the player reported `player_error` 150 for Rick and then for the PSY swap — nothing played. The receipt now reads
what the move ENDED in (`player_outcome.settled`) and names the refusal and its reason instead.

Disarm: with `_outcome_line` returning "" the first test goes red (the old «Suena ahora» comes back); with the wire
in `probe.py` back to the sync `complete_probe(` the last one goes red.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from i18n import langs
from nucleo.flash import player_outcome as PO
from nucleo.turn import reply_receipts as RR


def _owed(said, ops, lang=None):
    out = RR.player_owed(said, ops, lang)
    return out[0].said if out else ""


async def _settled(said, ops, lang=None):
    out = await RR.player(said, ops, lang)
    return out[0].said if out else ""

ENGINE = Path(__file__).resolve().parents[4]
RICK = {"videoId": "dQw4w9WgXcQ", "title": "Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)"}
PSY = {"videoId": "9bZkp7q19f0", "title": "PSY - GANGNAM STYLE(강남스타일) M/V"}


def _states():
    loaded = {"list": [RICK, PSY], "pos": 0, "videoId": RICK["videoId"], "title": RICK["title"], "player_error": "",
              "blocked_notice": {}, "blocked_videos": []}
    swapped = {**loaded, "pos": 1, "videoId": PSY["videoId"], "title": PSY["title"],
               "blocked_videos": [{"videoId": RICK["videoId"]}],
               "blocked_notice": {"kind": "swapped", "from": RICK["title"], "to": PSY["title"]}}
    exhausted = {**swapped, "player_error": "150", "blocked_videos": [{"videoId": RICK["videoId"]},
                                                                     {"videoId": PSY["videoId"]}],
                 "blocked_notice": {"kind": "exhausted", "from": PSY["title"]}}
    return [loaded, loaded, swapped, swapped, exhausted]


@pytest.fixture
def player_refuses(monkeypatch):
    from widgets import store
    seq = _states()
    monkeypatch.setattr(store, "load", lambda wid, *a, **k: dict(seq.pop(0) if len(seq) > 1 else seq[0])
                        if wid == "youtube" else {})
    monkeypatch.setattr(PO, "_on_screen", lambda card: True)
    monkeypatch.setattr(PO, "_POLL_S", 0.01)


def test_a_next_the_player_refused_names_the_refusal_and_why_never_now_playing(player_refuses):
    line = asyncio.run(_settled("Vale, salto al siguiente.", [("youtube", "next")], lang=langs.spec("es")))
    assert "Suena ahora" not in line
    assert line.startswith("No he podido ponerlo") and "propietario" in line
    assert RICK["title"] in line and PSY["title"] in line, line


def test_the_refusal_is_owed_even_over_a_reply_that_claimed_the_title(player_refuses):
    line = asyncio.run(_settled(f"Skipped, «{PSY['title']}» is on.", [("youtube", "next")],
                                       lang=langs.spec("en")))
    assert line.startswith("I couldn't play it") and "owner" in line


def test_a_move_the_player_kept_is_still_receipted_as_playing(monkeypatch):
    from widgets import store
    db = {"list": [RICK, PSY], "pos": 1, "videoId": PSY["videoId"], "title": PSY["title"]}
    monkeypatch.setattr(store, "load", lambda wid, *a, **k: dict(db) if wid == "youtube" else {})
    monkeypatch.setattr(PO, "_on_screen", lambda card: False)
    assert asyncio.run(_settled("Okay.", [("youtube", "next")], lang=langs.spec("en"))) == \
        f"Now playing: «{PSY['title']}»."


