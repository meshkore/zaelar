"""A reply that ignored the next/pause/add he asked for gets the transport receipt (2026-10-11).

`build-a-video-playlist-from-links__us`, turn 3: «I'm Sam, I'm in Austin. anyway skip to the next one» — `youtube:next`
ran, the player moved to PSY, and the reply was «Got it, Sam — Austin it is.». `card_receipt` (V2-781) only replaces
content-free acks; a reply WITH content that answered the side remark slipped through, and he had to ask «did you
actually skip it? what's playing now».

Disarm: with `owed` returning "" the first two tests go red; with the `complete_probe` call removed from `probe.py`
the wire test goes red.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from i18n import langs
from nucleo.flash import transport_receipt as TR

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
    assert TR.owed(REPLY, ops, lang=langs.spec("en")) == f"Now playing: «{PSY['title']}»."
    assert TR.owed(REPLY, ops, lang=langs.spec("es")) == f"Suena ahora «{PSY['title']}»."


def test_a_reply_that_already_names_the_title_owes_nothing(player_on_psy):
    assert TR.owed("Skipped — Gangnam Style is on now, Sam.", [("youtube", "next")], lang=langs.spec("en")) == ""
    assert TR.owed("I couldn't skip it.", [], lang=langs.spec("en")) == "", "a failed op is named elsewhere"
    assert TR.owed(REPLY, [("agenda", "add_meeting")], lang=langs.spec("en")) == "", "not a player"
    assert TR.owed(REPLY, [("youtube", "set_volume")], lang=langs.spec("en")) == "", "not a transport op"


def test_a_pause_and_an_add_have_their_own_receipts(player_on_psy, monkeypatch):
    player_on_psy["paused"] = True
    assert TR.owed("Sure thing.", [("youtube", "pause")], lang=langs.spec("en")) == f"Paused «{PSY['title']}»."
    assert TR.owed("Sure thing.", [("youtube", "add")], lang=langs.spec("en")) == \
        f"The queue now has 2: «{RICK['title'][:60]}» and «{PSY['title'][:60]}»."   # few rows are named (2026-10-14)
    assert TR.owed("Added it — 2 in the queue.", [("youtube", "add")], lang=langs.spec("en")) == ""


def test_the_text_channel_appends_the_receipt_from_what_its_turn_ran(player_on_psy, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    parte = {"executed": "widget_data", "widget": "youtube", "act": "next",
             "ops": [{"widget": "youtube", "act": "next"}], "answers": []}
    out = TR.complete_probe(REPLY, "widget_data", parte)
    assert out == f"{REPLY} Now playing: «{PSY['title']}»."
    assert TR.complete_probe(REPLY, "chat", None) == REPLY
    assert TR.complete_probe(REPLY, "widget_data", {"executed": "widget_data_failed", "fallidas": [{}]}) == REPLY


def test_the_voice_channel_reads_the_controls_his_turn_ran(player_on_psy, monkeypatch):
    from nucleo import canvas_focus
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    monkeypatch.setattr(canvas_focus, "this_turn_acts", lambda: [("youtube", "control", "next")])
    assert TR.voice_owed(REPLY) == f"Now playing: «{PSY['title']}»."
    monkeypatch.setattr(canvas_focus, "this_turn_acts", lambda: [("youtube", "show", "show")])
    assert TR.voice_owed(REPLY) == ""


def test_both_channels_are_wired():
    probe = (ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert "await _tr.complete_probe_settled(" in probe and "return_extra_exec)" in probe
    settle = (ENGINE / "nucleo/flash/post_stream_settle.py").read_text(encoding="utf-8")
    assert "transport_receipt" in settle and "await _pst_tr.voice_owed_settled(spoken_text)" in settle
