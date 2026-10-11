"""`player_outcome.settled` answers with what the player made of the move, not with what the card accepted.

The ES round of `build-a-video-playlist-from-links` (2026-10-11): the card accepted `next` (Rick loaded), the player
refused it 1.0 s later and refused the PSY swap 0.6 s after that. A card on a screen is waited on — a refusal ends the
wait, a swap restarts it — and a card on no screen has no player to wait for.

Disarm: with the wait gate in `settled` short-circuited (`or True`) the swap/refusal test goes red (the first reading, «playing», comes back);
with the `refused.append` on a swap removed, the first refused title is lost and the same test goes red.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from nucleo.flash import player_outcome as PO

A = {"videoId": "aaaaaaaaaaa", "title": "First"}
B = {"videoId": "bbbbbbbbbbb", "title": "Second"}


def _fake(monkeypatch, seq, on_screen=True):
    from widgets import store
    monkeypatch.setattr(store, "load", lambda wid, *a, **k: dict(seq.pop(0) if len(seq) > 1 else seq[0]))
    monkeypatch.setattr(PO, "_on_screen", lambda card: on_screen)
    monkeypatch.setattr(PO, "_POLL_S", 0.01)


def test_a_refusal_after_a_swap_names_both_refused_videos(monkeypatch):
    playing = {"list": [A, B], "pos": 0, "videoId": A["videoId"], "title": A["title"]}
    swapped = {**playing, "pos": 1, "videoId": B["videoId"], "title": B["title"],
               "blocked_notice": {"kind": "swapped", "from": "First", "to": "Second"}}
    gone = {**swapped, "player_error": "150", "blocked_notice": {"kind": "exhausted", "from": "Second"}}
    _fake(monkeypatch, [playing, swapped, gone])
    out = asyncio.run(PO.settled("youtube", quiet_s=1.0))
    assert out["state"] == "blocked" and out["refused"] == ["First", "Second"]


def test_a_quiet_player_means_it_plays(monkeypatch):
    _fake(monkeypatch, [{"list": [A], "pos": 0, "videoId": A["videoId"], "title": A["title"]}])
    t = time.monotonic()
    out = asyncio.run(PO.settled("youtube", quiet_s=0.05))
    assert out["state"] == "playing" and out["title"] == "First" and time.monotonic() - t < 1.0


def test_no_screen_no_wait_and_another_card_is_not_read(monkeypatch):
    _fake(monkeypatch, [{"videoId": A["videoId"], "title": "First"}], on_screen=False)
    t = time.monotonic()
    assert asyncio.run(PO.settled("youtube", quiet_s=5.0))["state"] == "playing"
    assert time.monotonic() - t < 1.0
    assert PO.outcome("musica")["state"] == ""


@pytest.mark.parametrize("db", [
    {"videoId": A["videoId"], "title": "First", "player_error": "150"},
    {"videoId": A["videoId"], "title": "First", "blocked_videos": [{"videoId": A["videoId"]}]},
    {"videoId": A["videoId"], "title": "First", "blocked_notice": {"kind": "explicit", "from": "First"}},
])
def test_every_sign_of_a_refusal_reads_as_blocked(monkeypatch, db):
    from widgets import store
    monkeypatch.setattr(store, "load", lambda wid, *a, **k: dict(db))
    assert PO.outcome("youtube") == {"state": "blocked", "title": "First", "to": ""}
