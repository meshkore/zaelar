"""«How's the game?» is the game errand he ordered — live or parked (node 2.459).

three-tasks-at-once (EN, 2026-10-11 02:58), t6: «car one looked good btw. how's the game?» → «Can't help with the game
score, though; that's not something I can see from here». The game had been dropped (node 2.457 is that cause), so
nothing named it. With the errand present the word is matched against it — its given NAME too (`errand_title`), not
only the brief — and a status about it names it as he asked it.
"""
from __future__ import annotations

import threading
import time
import types

import pytest

from nucleo import dispatch
from nucleo.dispatch import confirm as dc
from nucleo.turn import errands_of_a_turn as E
from nucleo.turn import named_errand

ASKED = "yeah the LG 27MP500 for $60 works, grab that. car one looked good btw. how's the game?"


def _brief(**verdicts):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {k: {"choice": c, "confidence": 0.99, "probs": {c: 0.99}}
                                    for k, c in verdicts.items()}, "_call_id": "t", "turn_id": "t", "open_ids": []}


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [
        {"id": "8", "request": "Construct a side-scrolling platformer card with coins and a higher jump",
         "phase": "creating a widget", "waiting_on": ""}])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(
        label="", title="Super Mario-style platformer game"))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})


def test_the_game_is_named_by_its_given_name(live):
    assert [e["id"] for e in named_errand.named(ASKED)] == ["8"], "«game» is in the name, not in the brief"


def test_a_status_about_it_says_its_name(live, monkeypatch):
    monkeypatch.setattr("i18n.langs.current_code", lambda: "en")
    line = E.status_owed(ASKED, _brief(wants_words="tell", request_type="question"))
    assert "Super Mario-style platformer game" in line and "Construct a side" not in line, line


def test_a_parked_game_is_named_too(monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [])
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {"6": {"request": "Build a small Super Mario-style platform game "
                                                       "widget", "context": {}, "ts": time.time(), "question": "?"}})
    assert [e["id"] for e in named_errand.named(ASKED)] == ["6"]
