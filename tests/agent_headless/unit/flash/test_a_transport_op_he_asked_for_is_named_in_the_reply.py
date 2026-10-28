"""A reply that ignored the next/pause/add he asked for gets the transport receipt (2026-10-11).

`build-a-video-playlist-from-links__us`, turn 3: «I'm Sam, I'm in Austin. anyway skip to the next one» — `youtube:next`
ran, the player moved to PSY, and the reply was «Got it, Sam — Austin it is.». `card_receipt` (V2-781) only replaces
content-free acks; a reply WITH content that answered the side remark slipped through, and he had to ask «did you
actually skip it? what's playing now».

Disarm: with `reply_receipts.player_owed` returning [] the first two tests go red.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from i18n import langs
from nucleo.turn import reply_receipts as RR


def _owed(said, ops, lang=None):
    out = RR.player_owed(said, ops, lang)
    return out[0].said if out else ""


async def _settled(said, ops, lang=None):
    out = await RR.player(said, ops, lang)
    return out[0].said if out else ""

ENGINE = Path(__file__).resolve().parents[4]
RICK = {"title": "Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)", "channel": "Rick Astley"}
PSY = {"title": "PSY - GANGNAM STYLE(강남스타일) M/V", "channel": "officialpsy"}
REPLY = "Got it, Sam — Austin it is."


@pytest.fixture
def player_on_psy(monkeypatch):
    from widgets import store
    db = {"list": [RICK, PSY], "pos": 1, "title": PSY["title"], "channel": PSY["channel"], "paused": False}
    monkeypatch.setattr(store, "load", lambda wid, *a, **k: dict(db) if wid == "youtube" else {})
    return db


def test_a_move_he_asked_for_names_what_is_playing_now_in_both_languages(player_on_psy):
    ops = [("youtube", "next")]
    assert _owed(REPLY, ops, lang=langs.spec("en")) == f"Now playing: «{PSY['title']}»."
    assert _owed(REPLY, ops, lang=langs.spec("es")) == f"Suena ahora «{PSY['title']}»."


def test_a_reply_that_already_names_the_title_owes_nothing(player_on_psy):
    assert _owed("Skipped — Gangnam Style is on now, Sam.", [("youtube", "next")], lang=langs.spec("en")) == ""
    assert _owed("I couldn't skip it.", [], lang=langs.spec("en")) == "", "a failed op is named elsewhere"
    assert _owed(REPLY, [("agenda", "add_meeting")], lang=langs.spec("en")) == "", "not a player"
    assert _owed(REPLY, [("youtube", "set_volume")], lang=langs.spec("en")) == "", "not a transport op"


def test_a_pause_and_an_add_have_their_own_receipts(player_on_psy, monkeypatch):
    player_on_psy["paused"] = True
    assert _owed("Sure thing.", [("youtube", "pause")], lang=langs.spec("en")) == f"Paused «{PSY['title']}»."
    assert _owed("Sure thing.", [("youtube", "add")], lang=langs.spec("en")) == \
        f"The queue now has 2: «{RICK['title'][:60]}» and «{PSY['title'][:60]}»."   # few rows are named (2026-10-14)
    assert _owed("Added it — 2 in the queue.", [("youtube", "add")], lang=langs.spec("en")) == ""


def test_the_voice_channel_reads_the_controls_his_turn_ran(player_on_psy, monkeypatch):
    from nucleo import canvas_focus
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    monkeypatch.setattr(canvas_focus, "this_turn_acts", lambda: [("youtube", "control", "next")])
    assert _owed(REPLY, RR._turn_acts("control")) == f"Now playing: «{PSY['title']}»."
    monkeypatch.setattr(canvas_focus, "this_turn_acts", lambda: [("youtube", "show", "show")])
    assert _owed(REPLY, RR._turn_acts("control")) == ""


