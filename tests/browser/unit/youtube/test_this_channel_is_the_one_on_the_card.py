"""«Bloquéame este canal» blocks the channel ON THE CARD, and a pasted link from it still plays, with a notice.

`video-blocked-channel-respected` (ES + EN, 2026-10-10): the order names no channel. `block_channel` stored the
string it was handed, so the brain had to know the name: the EN turn fell back to a style directive («Done — I'll
leave YouTube cooking channels out»), the ES one sent a Brain Worker probing nonexistent widgets for 210 s. The
referent is what the card shows — the playing video's author, a numbered row, or the one channel in sight — and
when several are in sight the widget asks which, naming them. An explicit link from a blocked channel is an order
(V2-604) and plays, and the card says once that it is from a channel he blocked.
"""
import json
from pathlib import Path

import pytest

from widgets import store
from widgets.youtube import data as yt

ENGINE = Path(__file__).resolve().parents[4]
_ROWS = [{"videoId": "AAAAAAAAAA1", "title": "Paella en 10 minutos", "channel": "Cocina Express con Leo"},
         {"videoId": "BBBBBBBBBB2", "title": "Ferrari F40 a fondo", "channel": "Motor Clasico"},
         {"videoId": "CCCCCCCCCC3", "title": "Croquetas caseras", "channel": "Cocina Express con Leo"}]


@pytest.fixture
def card(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(yt, "_oembed_title", lambda vid: {"title": "", "channel": ""})   # offline: no oembed

    def _put(**fields):
        db = yt._load(); db.update(fields); store.save(yt.WID, db)
    return _put


def _playing(card):
    card(videoId="AAAAAAAAAA1", title="Paella en 10 minutos", channel="Cocina Express con Leo",
         suggested=[dict(r) for r in _ROWS])


@pytest.mark.parametrize("said", ["", "este canal", "this channel", "ese", "that one"])
def test_a_pointer_blocks_the_playing_videos_channel_and_names_it(card, said):
    _playing(card)
    r = yt.apply_action("block_channel", {"channel": said} if said else {})
    assert r["ok"] and r["channel"] == "Cocina Express con Leo", r
    assert "Cocina Express con Leo" in r["message"]
    d = yt.view_data()
    assert d["blocked_channels"] == ["Cocina Express con Leo"]
    assert [s["channel"] for s in d["suggested"]] == ["Motor Clasico"]          # swept from home
    assert d["videoId"] == "AAAAAAAAAA1"                                         # what plays keeps playing


def test_a_row_number_names_that_rows_channel(card):
    card(search_results=[dict(r) for r in _ROWS])
    r = yt.apply_action("block_channel", {"channel": "2"})
    assert r["ok"] and r["channel"] == "Motor Clasico"


def test_a_fragment_is_stored_as_the_card_shows_it(card):
    _playing(card)
    assert yt.apply_action("block_channel", {"channel": "cocina express"})["channel"] == "Cocina Express con Leo"


def test_several_channels_in_sight_and_no_video_asks_which_naming_them(card):
    card(suggested=[dict(r) for r in _ROWS])
    r = yt.apply_action("block_channel", {"channel": "este canal"})
    assert r["ok"] is False and r["error"] == "which_channel"
    assert r["candidates"] == ["Cocina Express con Leo", "Motor Clasico"]
    assert "Motor Clasico" in r["message"] and not yt.view_data()["blocked_channels"]


def test_nothing_in_sight_asks_for_the_name_and_blocks_nothing(card):
    r = yt.apply_action("block_channel", {})
    assert r["ok"] is False and r["error"] == "no_channel" and not yt.view_data()["blocked_channels"]


def test_a_name_he_says_is_blocked_as_said(card):
    r = yt.apply_action("block_channel", {"channel": "Lucid AI Cars"})
    assert r["ok"] and yt.view_data()["blocked_channels"] == ["Lucid AI Cars"]


def test_a_pasted_link_from_a_blocked_channel_plays_with_a_notice(card):
    _playing(card)
    yt.apply_action("block_channel", {})
    card(list=[dict(_ROWS[2])])                    # he still has its link (the card's row knows the author)
    r = yt.apply_action("load", {"url": "https://youtu.be/CCCCCCCCCC3"})
    d = yt.view_data()
    assert r["ok"] and d["videoId"] == "CCCCCCCCCC3" and d["paused"] is False
    assert r["notice"] == "channel_blocked" and "Cocina Express con Leo" in r["message"]
    assert d["blocked_notice"]["kind"] == "channel_blocked"
    assert "BLOQUEÓ" in yt.prompt_digest()


def test_a_link_from_a_channel_he_did_not_block_carries_no_notice(card):
    _playing(card)
    yt.apply_action("block_channel", {"channel": "Motor Clasico"})
    r = yt.apply_action("load", {"url": "https://youtu.be/CCCCCCCCCC3"})
    assert r["ok"] and "notice" not in r and not yt.view_data()["blocked_notice"]


def test_unblock_gives_it_back_and_a_pointer_with_one_blocked_names_it(card):
    _playing(card)
    yt.apply_action("block_channel", {})
    r = yt.apply_action("unblock_channel", {"channel": "ese canal"})
    assert r["ok"] and r["channel"] == "Cocina Express con Leo" and not yt.view_data()["blocked_channels"]


def test_the_digest_names_the_playing_channel_and_keeps_the_queue(card):
    _playing(card)
    card(list=[dict(_ROWS[1])])
    dig = yt.prompt_digest()
    assert "canal «Cocina Express con Leo»" in dig and "Ferrari F40 a fondo" in dig


def test_the_router_reads_block_channel_for_the_orders_words():
    m = json.loads((ENGINE / "widgets/youtube/manifest.json").read_text(encoding="utf-8"))
    from nucleo.flash.turn_brief import MAX_DESC_CHARS
    desc = m["actions"]["block_channel"]["desc"]
    assert len(desc) <= MAX_DESC_CHARS                       # a descriptor cut short does not route
    for words in ("sugieras", "block this channel", "SIN canal"):
        assert words in desc


def test_a_style_rule_says_a_card_filter_is_not_one():
    from nucleo.flash import router_catalog
    tool = next(t for t in router_catalog.TOOLS if t["function"]["name"] == "set_style_directive")
    assert "block_channel" in tool["function"]["description"]
