"""The in-turn mouth speaks the row's state after the acts, never a stop that did not happen (V2-852 T04, I4).

Measured in session c8a307fd: a stop verdict unsure (0.47), the model called `stop_worker` and wrote «Understood —
stopping it. Nothing is running now»; the door vetoed the call (context-bleed) and the words were said anyway while the
search ran twenty more minutes. Words written while a stop verdict is in play now wait for the stop's door
(`Hold` + `stop.say_the_row`): a stop that ran keeps them, a refused one is replaced by the rows' state by title, and a
turn that never called the stop door says its words as written. Variants: another domain, Spanish, a stop that ran.
"""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

from nucleo.flash import follow_up_pass as fup
from nucleo.request import stop as sd
from nucleo.request import stop_row as sr
from nucleo.turn import brief as _tb


def _brief(choice: str, confidence: float):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [],
            "result": {_tb.REQUEST_KEY: {"choice": "order", "confidence": 0.9}, sd.KEY: {"choice": choice, "confidence": confidence}}}


@pytest.fixture
def one_row(monkeypatch):
    from nucleo import dispatch
    rec = SimpleNamespace(task_id="4", title="Lisbon flat under 1200", goal="find a flat in Lisbon")
    monkeypatch.setattr(dispatch, "resolve_sessions", lambda q: ["4"])
    monkeypatch.setattr(dispatch, "get_record", lambda t: rec if t == "4" else None)
    return rec


def _turn(brief, words: str, *, called_stop: bool, stop_ran: bool):
    sent, events = [], []
    emit = lambda kind, label="", **kw: events.append(label)  # noqa: E731
    hold = fup.Hold(brief, sent.append)
    hold.say(words)
    calls = [{"name": "stop_worker", "args": {}}] if called_stop else []
    asyncio.run(hold.release(calls, [], emit))
    said_in_stream = list(sent)
    out = sr.say_the_row(hold, {"v": "stop" if stop_ran else None}, SimpleNamespace(_turn_calls=calls), sent,
                         sent.append, emit)
    return said_in_stream, sent, out


@pytest.mark.parametrize("words", ["Understood — stopping it. Nothing is running now.", "Vale, la paro. Ya no hay nada en marcha."])
def test_a_refused_stop_is_never_said_and_the_row_is(one_row, words):
    said_in_stream, sent, out = _turn(_brief("stop", 0.47), words, called_stop=True, stop_ran=False)
    assert said_in_stream == [], "the words narrating the stop went out before its door ruled"
    assert words not in sent, "a stop the door refused was said"
    assert sent and "Lisbon flat under 1200" in sent[-1], f"the rows' state was not said by the row's title: {sent}"


def test_a_stop_that_ran_keeps_its_words(one_row):
    _, sent, _ = _turn(_brief("stop", 0.9), "Stopping the flat search.", called_stop=True, stop_ran=True)
    assert sent == ["Stopping the flat search."]


def test_words_with_no_call_to_the_stop_door_are_said_as_written(one_row):
    _, sent, _ = _turn(_brief("stop", 0.3), "It has found 40 flats so far.", called_stop=False, stop_ran=False)
    assert sent == ["It has found 40 flats so far."]


def test_a_turn_with_no_stop_in_play_is_not_held(one_row):
    sent: list = []
    hold = fup.Hold(_brief("keep", 0.9), sent.append)
    hold.say("Here is the weather.")
    assert sent == ["Here is the weather."], "a turn with no stop in play waited for nothing"


def test_the_turn_says_the_row_after_its_acts():
    """Wired where the acts have run: after the post-stream chain (the backstop, the clarify) and before the close."""
    import inspect

    from nucleo.turn import pipeline
    src = inspect.getsource(pipeline.run)
    assert src.index("_post_stream.run(") < src.index("_stop_row.say_the_row(") < src.index("close_the_turn(")
