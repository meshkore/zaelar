"""«Close the widget.» over several open cards goes to the card his previous turn acted on — while that turn is recent —
and otherwise ASKS which one, never guesses and never claims (node 2.914).

Live, 2026-10-28 16:00 (T74-T76): «Stop the music right now.» then, six seconds later, «Close the widget.» with the music
card and a document being written side by side. The canvas verdict was `close` at 1.00, no card was named, the only-card
backstop needs ONE card, and the reply said «the music player's closed» over a card that stayed. The operator's rule: an
unnamed order means the card he just interacted with; after a while the screen is a set of cards again and it asks.

Disarm: with `canvas_focus.last_turn_card_recent` answering "", the first test goes red.
"""
from __future__ import annotations

import threading
import time

import pytest

from nucleo import canvas_focus
from nucleo.flash import close_guards
from nucleo.turn import brief as _tb

OPEN = ["musica", "documento"]


def _brief(answers: dict):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": list(OPEN),
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


@pytest.fixture
def his_previous_turn_touched_the_music():
    """Two of his turns through the funnel: the first paused the music, the second is the one under test."""
    canvas_focus._reset()
    canvas_focus.note("transcript", "", role="user")
    canvas_focus.note("widget", "data:pause", extra={"id": "musica", "src": "flash"})
    canvas_focus.note("transcript", "", role="user")
    yield
    canvas_focus._reset()


def test_seconds_after_stopping_the_music_close_the_widget_is_the_music(his_previous_turn_touched_the_music):
    b = _brief({_tb.CANVAS_KEY: ("close", 1.0)})
    assert close_guards.the_card_he_means("Close the widget.", OPEN, brief=b) == "musica"


def test_minutes_later_it_asks_which_one_by_their_names(his_previous_turn_touched_the_music, monkeypatch):
    with canvas_focus._lock:
        canvas_focus._state["t_prev"] -= canvas_focus.RECENT_S + 60
    b = _brief({_tb.CANVAS_KEY: ("close", 1.0)})
    assert close_guards.the_card_he_means("Close the widget.", OPEN, brief=b) == ""

    class _Say:
        ask_which_item = "Which one? I have {cands}."
    q = close_guards.which_card_question("Close the widget.", OPEN, brief=b, say=lambda: _Say)
    assert q.startswith("Which one? I have ") and "," in q


def test_a_close_the_verdict_is_not_sure_of_neither_closes_nor_asks(his_previous_turn_touched_the_music):
    b = _brief({_tb.CANVAS_KEY: ("close", 0.6)})
    assert close_guards.the_card_he_means("Close the widget.", OPEN, brief=b) == ""
    assert close_guards.which_card_question("Close the widget.", OPEN, brief=b, say=lambda: None) == ""


def test_a_long_sentence_is_not_an_unnamed_close(his_previous_turn_touched_the_music):
    b = _brief({_tb.CANVAS_KEY: ("close", 1.0)})
    said = "I still see the music in my UI, this happened before a lot of times, so maybe it is time you fix that"
    assert close_guards.the_card_he_means(said, OPEN, brief=b) == ""
