"""V2-781 — «close the video and keep the music going» left the music paused.

Measured in `tres-tarjetas-y-el-video-por-alusion` (ES and EN, 2026-10-10): the trailer took the speaker and
channel exclusivity paused the background music (`youtube toma «audio» → calla musica`, V2-092 — right: there is
one speaker). Then he closed the video «and keep the music going», the reply said «Done», and the round ended with
the music still `paused: true` and the closed video still reading as playing. Nothing ever gave the speaker back.

The mechanism is the exclusivity's other half: a widget that SILENCED others to take a channel hands it back when
it leaves it — its card closed, or an action that ends its production (the player's `close`). What it silenced
resumes through its DECLARED `resume` action (`runtime.resume`; a widget that declares none is never resumed). A
pause is not leaving: «pause the trailer a second» keeps the music quiet. And anything the operator did to the
silenced widget himself since (paused it, played it) is his decision, so that one is not handed anything.
"""
from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from widgets import producers

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def desk(monkeypatch):
    man = [
        {"id": "vid", "runtime": {"output": "audio", "produce": ["play", "load"], "suspend": "pause",
                                  "resume": "play", "active_when": {"paused": False}}},
        {"id": "mus", "runtime": {"output": "audio", "produce": ["play", "resume"], "suspend": "pause",
                                  "resume": "resume", "active_when": {"paused": False}}},
        {"id": "pod", "runtime": {"output": "audio", "produce": ["play"], "suspend": "pause",
                                  "active_when": {"paused": False}}},
    ]
    monkeypatch.setattr(producers.runtime, "catalog", lambda: man)
    monkeypatch.setattr(producers.runtime, "get", lambda wid: next((w for w in man if w["id"] == wid), None))

    class Bus:
        playing: set = set()
        sent: list = []

        async def view(self, wid):
            return {"paused": wid not in self.playing}

        async def dispatch(self, wid, action, payload):
            self.sent.append((wid, action))
            if action == "pause":
                self.playing.discard(wid)
            if action in ("play", "resume"):
                self.playing.add(wid)
            return {"ok": True}

    b = Bus()
    b.playing, b.sent = {"mus"}, []
    monkeypatch.setattr(producers, "_view_data", b.view)
    import widgets.server_api as sapi
    monkeypatch.setattr(sapi, "dispatch_raw", b.dispatch)
    producers._HELD.clear()
    yield b
    producers._HELD.clear()


def _take(b, wid="vid"):
    b.playing.add(wid)
    return asyncio.run(producers.enforce_exclusive(wid, "play"))


def test_closing_the_card_that_took_the_speaker_gives_it_back(desk):
    assert _take(desk) == ["mus"]
    assert desk.playing == {"vid"}
    resumed = asyncio.run(producers.hand_back("vid"))
    assert resumed == ["mus"]
    assert desk.playing == {"mus"}                       # the closed card stopped, the music came back
    assert ("vid", "pause") in desk.sent and ("mus", "resume") in desk.sent


def test_a_pause_is_not_leaving(desk):
    _take(desk)
    desk.playing.discard("vid")                          # the pause reached the player
    asyncio.run(producers.after_action("vid", "pause"))
    assert desk.playing == set()                         # music stays quiet while the trailer is paused
    assert ("mus", "resume") not in desk.sent


def test_an_action_that_ends_production_gives_it_back(desk):
    _take(desk)
    desk.playing.discard("vid")                          # e.g. the player's `close` emptied it
    asyncio.run(producers.after_action("vid", "close"))
    assert desk.playing == {"mus"}


def test_what_he_did_to_the_silenced_card_himself_stands(desk):
    _take(desk)
    asyncio.run(producers.after_action("mus", "pause"))  # he paused the music himself meanwhile
    assert asyncio.run(producers.hand_back("vid")) == []
    assert "mus" not in desk.playing


def test_a_widget_that_declares_no_resume_is_never_resumed(desk):
    desk.playing = {"pod"}
    assert _take(desk) == ["pod"]
    assert asyncio.run(producers.hand_back("vid")) == []
    assert "pod" not in desk.playing


def test_nothing_held_means_nothing_handed(desk):
    assert asyncio.run(producers.hand_back("vid")) == []


@pytest.mark.parametrize("wid", ["youtube", "musica"])
def test_the_real_players_declare_an_existing_resume_action(wid):
    man = json.loads((ENGINE / "widgets" / wid / "manifest.json").read_text(encoding="utf-8"))
    sp = producers.spec(man)
    assert sp["resume"] in set(man.get("actions") or {}), wid


def test_an_operator_close_hands_the_speaker_back():
    """Every operator close passes `canvas_closes.note` (fed by `voice.observer.emit`); it asks for the hand-back."""
    src = (ENGINE / "nucleo" / "canvas_closes.py").read_text(encoding="utf-8")
    assert "hand_back" in src
    assert "after_action" in (ENGINE / "widgets" / "server_api.py").read_text(encoding="utf-8")
