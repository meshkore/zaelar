"""The first-rows notice waits for a turn in flight and for a stop's hush, then goes through `proactive.notify`
once, with its own event (node 2.680)."""
from __future__ import annotations

import asyncio

import pytest

from i18n import langs
from nucleo.turn import first_rows_notice as frn
from voice import observer, proactive

ERRAND = {"id": "w3", "request": "Find an apartment in the Mission", "secs": 200, "sheet": "ef56-w3"}
ROWS = [{"title": "Sunny 2BR on Valencia St", "price": "$3,400", "url": "https://zillow.com/1"}]


def _ev(t, role, text):
    return {"t_ms": t, "kind": "brain", "role": role, "text": text, "wall": "you" if role == "user" else "agent"}


@pytest.fixture
def world(monkeypatch):
    frn.forget()
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("en"))
    monkeypatch.setattr(frn, "_POLL_S", 0.0)
    monkeypatch.setattr(frn, "_errand_of", lambda sheet: ERRAND)
    from widgets.results import data as sheet_data
    monkeypatch.setattr(sheet_data, "view_data", lambda sheet: {"title": "Mission flats", "items": ROWS})
    sent, emitted = [], []

    async def _notify(title, text, **kw):
        sent.append((text, kw.get("key")))
        return False

    monkeypatch.setattr(proactive, "notify", _notify)
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: emitted.append((kind, label)))
    monkeypatch.setattr(observer, "now_ms", lambda: 10_000_000.0)
    state = {"events": [_ev(9_990_000, "user", "keep me posted")], "polls": 0, "hush": 0}

    def _events():
        state["polls"] += 1
        if state["polls"] >= 3 and len(state["events"]) == 1:
            state["events"].append(_ev(9_995_000, "assistant", "Will do."))   # the turn ends on the 3rd poll
        return list(state["events"])

    monkeypatch.setattr(observer, "debug_events", _events)

    def _hushed():
        state["hush"] += 1
        return state["hush"] <= 2

    monkeypatch.setattr(proactive, "hushed", _hushed)
    yield sent, emitted, state
    frn.forget()


def test_it_waits_for_the_turn_and_the_hush_then_says_it_once(world):
    sent, emitted, state = world
    assert asyncio.run(frn._run("ef56-w3", "w3")) is True
    assert state["polls"] >= 3 and state["hush"] >= 3
    assert sent == [("The first ones for «Mission flats» are in: Sunny 2BR on Valencia St — $3,400. They're on your "
                     "sheet.", "first_rows:w3")]
    assert ("widget", "🔔 first rows of the errand, told unprompted") in emitted
    assert asyncio.run(frn._run("ef56-w3", "w3")) is False        # never repeated
    assert len(sent) == 1


def test_a_turn_that_never_ends_gives_up_without_speaking(world, monkeypatch):
    sent, _, state = world
    monkeypatch.setattr(frn, "_MAX_WAIT_S", 0.0)
    monkeypatch.setattr(observer, "debug_events", lambda: [_ev(9_990_000, "user", "keep me posted")])
    assert asyncio.run(frn._run("ef56-w3", "w3")) is False
    assert sent == []
    assert "w3" not in frn._PENDING


def test_a_line_of_his_with_no_reply_yet_is_a_turn_in_flight(monkeypatch):
    frn.forget()
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("en"))
    events = [_ev(9_990_000, "user", "keep me posted"), _ev(9_991_000, "assistant", "Will do."),
              _ev(9_999_000, "user", "any news?")]
    said, why = frn.decide("ef56-w3", {"items": ROWS}, errand=ERRAND, events=events, now_ms=10_000_000.0)
    assert (said, why) == ("", "in flight")
