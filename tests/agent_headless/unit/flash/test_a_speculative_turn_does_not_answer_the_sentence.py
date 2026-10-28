"""A speculative turn that is replaced before its first word answers nothing (demo, 2026-10-22, 12:59:46).

LiveKit starts a turn on every STT final and, when more words come, replaces it with one carrying the whole
sentence. The replacement's `offer` ran 17 ms BEFORE the replaced turn's cancellation reached `unanswered`:

    46.232  «Hey, Johnny. Show me some videos of the SpaceX»          → act (speculative turn 1)
    46.925  «Hey, Johnny. Show me some videos of the SpaceX Starship tests.» → peeled to «Starship tests.»
    46.942  turn 1 cancelled, 0 chars said — too late to un-consume

The model asked for the video (its window had both halves) and the context-bleed guard, reading «Starship
tests.», dropped it. The words count as answered when the turn says its first word, whatever order the two
turns die and start in.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.input import stt as acc

HEAD = "Hey, Johnny. Show me some videos of the SpaceX"
WHOLE = "Hey, Johnny. Show me some videos of the SpaceX Starship tests."


@pytest.fixture
def a(monkeypatch):
    async def _judge(_t):
        return "complete", ""
    monkeypatch.setattr(acc, "_judge", _judge)
    monkeypatch.setattr(acc, "_predicate", lambda _t: (True, ""))   # both halves read as complete, as they did
    monkeypatch.setenv("ZAELAR_JEV", "0")
    return acc.Accumulator()


def _offer(a, text, t):
    return asyncio.run(a.offer(text, now=t))


def _brain(a):
    return type("B", (), {"_acc": a})()


def test_the_replacing_turn_gets_the_whole_sentence_before_the_old_one_dies(a):
    assert _offer(a, HEAD, 46.232)[:2] == ("act", HEAD)
    action, text, _, _ = _offer(a, WHOLE, 46.925)          # the race: turn 1 has not reported its death yet
    assert (action, text) == ("act", WHOLE), f"the sentence lost its head: {text!r}"
    acc.unanswered_by(_brain(a), HEAD)                       # the late cancellation changes nothing
    acc.answered_by(_brain(a))
    assert _offer(a, WHOLE + " Right now.", 50.0)[1] == "Right now."   # and WHOLE is now answered for good


def test_a_head_whose_turn_spoke_is_still_peeled(a):
    _offer(a, HEAD, 46.232)
    acc.answered_by(_brain(a))                               # turn 1 said its first word
    assert _offer(a, WHOLE, 46.925)[1] == "Starship tests."


def test_an_unrelated_sentence_does_not_bring_the_old_one_back(a):
    _offer(a, HEAD, 46.232)
    assert _offer(a, "What time is it?", 47.0)[1] == "What time is it?"


def test_the_provider_marks_the_answer_at_the_first_spoken_chunk():
    from tests import voice_turn_source as _vts
    src = _vts.turn_source()
    i = src.index("def send(txt: str):")
    assert "_acc_mod.answered_by(brain)" in src[i:i + 600]
