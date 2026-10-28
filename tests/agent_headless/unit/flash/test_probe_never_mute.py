"""A plain chat turn that comes back with no tool call and no text must not stay mute (2026-08-17, live bug found
running tests/use_cases' dynamic harness against `search-buy-used-car`): after several worker check-ins
("¿pudiste relanzarla?"), the FlashBrain gave one completely silent turn; the NEXT turn, seeing that gap in the
conversation window, ended up echoing the operator's own question back verbatim ("Dime algo, por favor. ¿Se
relanzó la búsqueda...?" — literally the tester's own words).

Found on the old text channel; since refactor2710-01 there is one turn, the voice turn, and these drive it whole
through the typed channel (`nucleo.cli.turn.run_turn`, dry) with a model that streams nothing and calls no tool.
"""
from __future__ import annotations

import pytest

from tests.brain import harness as H
from voice import brain_notes


@pytest.fixture(autouse=True)
def _drained_notes():
    brain_notes.drain()
    yield
    brain_notes.drain()


def _mute_turn(phrase: str) -> H.Outcome:
    return H.run_case({"id": "never-mute", "lang": "es", "phrase": phrase, "source": "2026-08-17",
                       "screen": {"open": []}, "expect": "talk", "model": {"say": ""}})


def test_mute_chat_turn_with_worker_active_falls_back_to_still_working_filler(monkeypatch):
    monkeypatch.setattr("nucleo.dispatch.has_active", lambda: True)

    question = "¿Va todo bien? ¿Pudiste relanzar la búsqueda o sigue atascada? Dime algo."
    out = _mute_turn(question)

    assert not out.error, out.error
    assert out.action == "chat", out.action
    assert out.reply                       # never mute
    assert out.reply != question           # never a verbatim echo of what the operator just said


def test_mute_chat_turn_with_nothing_running_asks_to_repeat(monkeypatch):
    monkeypatch.setattr("nucleo.dispatch.has_active", lambda: False)

    out = _mute_turn("hola")

    assert not out.error, out.error
    assert out.reply
