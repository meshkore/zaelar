"""A bare answer reaches the memory distiller WITH the question it answers.

rental-car-automatic-airport__us (2026-10-11): «where are you based?» → «San Francisco». The distiller saw the two
words alone, in the middle of a Denver car-rental errand, and filed «Plans to travel to San Francisco»;
`state.location` stayed empty and the introduction asked again eight turns later («San Francisco, I said that
earlier»). `nucleo/memory_agent/answer_frame.py` puts the agent's last question in front of a short answer; what the
answer means stays the distiller's reading.
"""
from __future__ import annotations

import time

import pytest

from nucleo.memory_agent import answer_frame as AF

ASKED_EN = ("Got it — I'll flag anything as soon as I have options. Meanwhile, quick one so I can set things "
            "up properly: where are you based?")


@pytest.mark.parametrize("reply,question", [
    (ASKED_EN, "Meanwhile, quick one so I can set things up properly: where are you based?"),
    ("Vale, lo miro. Por cierto, ¿de dónde eres?", "Por cierto, ¿de dónde eres?"),
    ("Perfecto, en cuanto tenga opciones te aviso.", ""),
])
def test_the_question_is_the_one_the_reply_ENDS_on(reply, question):
    assert AF._last_question(reply) == question


def test_a_short_answer_travels_with_the_question():
    out = AF.framed("San Francisco", asked=ASKED_EN)
    assert out.endswith("San Francisco") and "where are you based?" in out


@pytest.mark.parametrize("text", ["are these automatic? the jeep compass at 211 looks good if so",
                                  "wait, those dates aren't right — I need Monday to Friday, so the 12th"])
def test_a_question_or_a_sentence_of_his_own_is_left_alone(text):
    assert AF.framed(text, asked=ASKED_EN) == text


def test_a_reply_that_asked_nothing_frames_nothing():
    assert AF.framed("San Francisco", asked="Noted, I'll keep you posted.") == "San Francisco"


def test_an_old_question_is_no_longer_the_conversation_s_last_word(monkeypatch):
    from memory import api as _mem
    monkeypatch.setattr(_mem, "recent_window", lambda limit=1: [
        {"role": "user", "content": "ok", "ts": time.time() - 3600},
        {"role": "assistant", "content": ASKED_EN, "ts": time.time() - 3600}])
    assert AF.asked_before() == ""
    monkeypatch.setattr(_mem, "recent_window", lambda limit=1: [
        {"role": "assistant", "content": ASKED_EN, "ts": time.time() - 5}])
    assert "where are you based?" in AF.asked_before()
