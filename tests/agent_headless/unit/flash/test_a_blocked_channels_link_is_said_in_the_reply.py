"""Node 2.716 — the reply that let a blocked channel's pasted link through SAYS so, in his language, on both channels.

`video-blocked-channel-respected` (2026-10-14, ES+EN 3/5): the video was queued/played — the explicit order wins, which
is right — and the reply never warned («it's already loaded, nothing new to start»). The card stamps the fact
(`widgets.youtube.blocked_order`); the mouth (`nucleo/turn/reply_receipts.blocked_channel`, refactor2710-03) reads
it in a turn whose orders touched the player, consumes it, and says it as the act's own `met` line — once.

Disarm: make the player-act check in `blocked_channel` false → every «owes» test goes red.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from i18n import langs
from nucleo import canvas_focus
from nucleo.turn import reply, reply_receipts as RR
from widgets import store


@pytest.fixture
def card(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    canvas_focus._reset()
    db = {"blocked_channels": ["Rick Astley"],
          "blocked_order": {"channel": "Rick Astley", "title": "Together Forever", "queued": True, "at": time.time()}}
    store.save("youtube", db)
    yield db
    canvas_focus._reset()


def _turn(action: str = "add") -> None:
    canvas_focus.note("transcript", "", role="user")
    canvas_focus.note("widget", f"data:{action}", extra={"id": "youtube", "src": "probe"})


def _owed() -> str:
    out = asyncio.run(RR.blocked_channel())
    return out[0].said if out else ""


def test_the_reply_owes_the_warning_in_spanish_once(card, monkeypatch):
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("es"))
    _turn()
    out = _owed()
    assert "«Rick Astley», el canal que bloqueaste" in out and "lo añado porque me lo has pedido" in out
    assert _owed() == ""                                                      # consumed: said once


def test_a_played_link_owes_the_english_line(card, monkeypatch):
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("en"))
    card["blocked_order"]["queued"] = False
    store.save("youtube", card)
    _turn("load")
    assert _owed() == "Heads up: that video is from «Rick Astley», the channel you blocked — playing it because you asked."


def test_a_turn_that_did_not_touch_the_player_reads_nothing(card, monkeypatch):
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("en"))
    canvas_focus.note("transcript", "", role="user")
    assert _owed() == ""
    assert store.load("youtube").get("blocked_order")                         # left for the turn that owns it


def test_the_mouth_says_it_after_the_streamed_words(card, monkeypatch):
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("en"))
    _turn()
    sent: list[str] = []

    class _Speech:
        @staticmethod
        def sanitize(s, drop_metadata=False):
            return s

    said = asyncio.run(reply.after_acts((), "Added.", sent.append, _Speech))
    assert len(sent) == 1 and "the channel you blocked" in sent[0] and said == "Added. " + sent[0].strip()
