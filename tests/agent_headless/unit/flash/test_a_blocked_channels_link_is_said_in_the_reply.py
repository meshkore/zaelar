"""Node 2.716 — the reply that let a blocked channel's pasted link through SAYS so, in his language, on both channels.

`video-blocked-channel-respected` (2026-10-14, ES+EN 3/5): the video was queued/played — the explicit order wins, which
is right — and the reply never warned («it's already loaded, nothing new to start»). The card stamps the fact
(`widgets.youtube.blocked_order`); `blocked_channel_receipt` reads it in a turn whose orders touched the player,
consumes it, and appends the sentence unless the reply already speaks of the block.

Disarm: make `_may_owe` return False → every «owes» test goes red; drop the `_SAYS_BLOCK` check → the «already said»
test goes red.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from i18n import langs
from nucleo import canvas_focus
from nucleo.flash import blocked_channel_receipt as BCR
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


def test_the_text_reply_owes_the_warning_in_spanish(card, monkeypatch):
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("es"))
    _turn()
    out = BCR.complete("La cola tiene ahora 2.")
    assert out.startswith("La cola tiene ahora 2. ") and "«Rick Astley», el canal que bloqueaste" in out
    assert "lo añado porque me lo has pedido" in out
    assert BCR.complete("Hecho.") == "Hecho."                                  # consumed: said once


def test_a_played_link_owes_the_english_line(card):
    card["blocked_order"]["queued"] = False
    store.save("youtube", card)
    _turn("load")
    assert BCR.owed("It's up.", lang=langs.spec("en")) == \
        "Heads up: that video is from «Rick Astley», the channel you blocked — playing it because you asked."


def test_a_reply_that_already_speaks_of_the_block_owes_nothing(card):
    _turn()
    assert BCR.owed("Queued it, though it's from a channel you blocked.", lang=langs.spec("en")) == ""


def test_a_turn_that_did_not_touch_the_player_reads_nothing(card):
    canvas_focus.note("transcript", "", role="user")
    assert BCR.owed("Sure.", lang=langs.spec("en")) == ""
    assert store.load("youtube").get("blocked_order")                         # left for the turn that owns it


def test_the_voice_rail_says_it_after_the_streamed_words(card, monkeypatch):
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("en"))
    _turn()
    sent: list[str] = []

    class _Speech:
        @staticmethod
        def sanitize(s, drop_metadata=False):
            return s

    said = asyncio.run(BCR.said_after("Added.", sent.append, _Speech))
    assert len(sent) == 1 and "the channel you blocked" in sent[0] and said == "Added. " + sent[0]


def test_the_voice_turn_is_wired():
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]
    settle = (root / "nucleo/flash/post_stream_settle.py").read_text(encoding="utf-8")
    assert "await _pst_bcr.said_after(" in settle
