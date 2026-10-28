"""A typed order waits for the spoken sentence that began BEFORE it (demo, 2026-10-22).

«ok just put that away for now…» by voice, the wallpaper request pasted a second later: the paste's turn started
first, the voice turn's end-of-turn interrupted it, and the wallpaper errand was lost. Turns run in the order he
STARTED them; voice begun after the text stays an ordinary barge-in; the wait is bounded.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from voice.engine.pipeline import agent_events
from nucleo.input import typed as order


@pytest.fixture(autouse=True)
def _clean():
    order.reset()
    yield
    order.reset()


def test_a_text_inside_an_open_utterance_waits_until_it_is_a_turn():
    order.note_onset(10.0)
    order.note_end(12.0)                        # he stopped; the endpointing is still deciding
    assert order.must_wait(12.5, 12.5)
    order.note_committed(13.2)                  # the voice turn is in
    assert not order.must_wait(12.5, 13.3)


def test_voice_begun_after_the_text_does_not_hold_it():
    order.note_committed(5.0)
    assert not order.must_wait(10.0, 10.0)      # nothing open: the text goes at once
    order.note_onset(10.5)                      # he starts talking AFTER the paste
    assert not order.must_wait(10.0, 10.6)


def test_a_new_utterance_while_waiting_does_not_jump_the_queue():
    order.note_onset(10.0)
    assert order.must_wait(11.0, 11.0)
    order.note_committed(12.0)
    order.note_onset(12.5)                      # a second sentence, begun after the text
    assert not order.must_wait(11.0, 12.6)


def test_the_wait_is_bounded_by_silence_and_by_the_cap():
    order.note_onset(10.0)
    order.note_end(11.0)                        # noise: no turn will ever commit
    assert order.must_wait(11.5, 11.5)
    assert not order.must_wait(11.5, 11.0 + order.SILENT_GRACE_S + 0.1)
    order.reset()
    order.note_onset(10.0)                      # a microphone that never goes quiet
    assert not order.must_wait(10.5, 10.5 + order.CAP_S + 0.1)


class _Session:
    def __init__(self):
        self.replies: list[str] = []

    def generate_reply(self, *, user_input: str):
        self.replies.append(user_input)


def _packet(text: str):
    return SimpleNamespace(topic="zaelar-text",
                           data=json.dumps({"t": "zaelar-text", "text": text}).encode("utf-8"))


def test_the_handler_queues_the_paste_behind_the_voice_turn():
    """The wiring: the real data handler holds the paste, the user item releases it."""
    async def run():
        s, said = _Session(), []
        emit = lambda *a, **k: said.append(a[1] if len(a) > 1 else "")   # noqa: E731
        agent_events._on_user_state(SimpleNamespace(new_state="speaking"), _busy={"bot": False, "user": False},
                                    _emit=emit, _onset={"voice_ended": 0.0},
                                    sm=SimpleNamespace(on_user_state=lambda *_: None))
        agent_events._on_data(_packet("find me the orion nebula wallpaper"), _emit=emit, _json=json, _wake={},
                              session=s)
        await asyncio.sleep(0.25)
        assert s.replies == [], "the paste ran before the sentence he had begun saying"
        agent_events._on_item(SimpleNamespace(item=SimpleNamespace(role="user", text_content="put that away")),
                              _emit=emit)
        await asyncio.sleep(0.25)
        assert s.replies == ["find me the orion nebula wallpaper"]
    asyncio.run(run())


def test_with_no_voice_open_the_paste_goes_at_once():
    s = _Session()
    agent_events._on_data(_packet("hello"), _emit=lambda *a, **k: None, _json=json, _wake={}, session=s)
    assert s.replies == ["hello"]
