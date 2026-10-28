"""Node 2.715 — a pasted link from a channel he BLOCKED goes through (queued or played) and the card stamps it.

`video-blocked-channel-respected` (2026-10-14, ES+EN 3/5): the explicit order wins over the standing filter (V2-604),
but `add` — the ES round's «ponme este» — wrote no notice at all, and nothing the reply could read said the link came
from the channel he had just blocked. Both doors now stamp `blocked_order` for `nucleo.turn.reply_receipts`
and return the notice; a link from an unblocked channel, or a NAME search, stamps nothing.

Disarm: make `blocked_order.stamp` a no-op → the stamp assertions go red; drop the `explicit_link_notice` call from
`_a_add` → the queue tests go red.
"""
import urllib.request

import pytest

from widgets import store
from widgets.youtube import blocked_order as BO
from widgets.youtube import data as yt

LINK = "https://www.youtube.com/watch?v=yPYZpwSpKmA"
HIST = {"videoId": "yPYZpwSpKmA", "title": "Rick Astley - Together Forever", "channel": "Rick Astley",
        "url": LINK, "played_at": 1, "plays": 1}


def _offline(*a, **k):
    raise OSError("offline")


@pytest.fixture
def blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(urllib.request, "urlopen", _offline)      # the card's own rows name the channel
    db = yt._load()
    db.update({"videoId": "dQw4w9WgXcQ", "title": "Never Gonna Give You Up", "channel": "Rick Astley",
               "history": [dict(HIST)]})
    store.save(yt.WID, db)
    assert yt.apply_action("block_channel", {})["channel"] == "Rick Astley"


def test_a_queued_link_from_the_blocked_channel_is_stamped_and_says_so(blocked):
    r = yt.apply_action("add", {"url": LINK})
    assert r["ok"] and r["notice"] == "channel_blocked" and "Rick Astley" in r["message"]
    stamp = store.load("youtube")["blocked_order"]
    assert stamp["channel"] == "Rick Astley" and stamp["queued"] is True
    assert BO.take()["channel"] == "Rick Astley" and BO.take() == {}            # said once


def test_a_repeated_add_of_that_link_still_stamps(blocked):
    yt.apply_action("add", {"url": LINK})
    BO.take()
    r = yt.apply_action("add", {"url": LINK})
    assert r["already_in_list"] and r["notice"] == "channel_blocked" and BO.pending()


def test_a_played_link_from_the_blocked_channel_is_stamped_and_bannered(blocked):
    r = yt.apply_action("load", {"url": LINK})
    assert r["notice"] == "channel_blocked"
    db = store.load("youtube")
    assert db["blocked_order"]["queued"] is False and db["blocked_notice"]["kind"] == "channel_blocked"


def test_a_link_from_another_channel_stamps_nothing(blocked):
    r = yt.apply_action("add", {"url": "https://youtu.be/9bZkp7q19f0", "title": "PSY"})
    assert r["ok"] and "notice" not in r and not BO.pending()


def test_a_stale_stamp_is_dropped_not_said(blocked):
    yt.apply_action("add", {"url": LINK})
    assert BO.take(max_age_s=-1) == {} and not BO.pending()
