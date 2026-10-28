"""A stop that names the ACTIVITY to stop is an order about it, not a silence order (bank case msg-en-mail-hide).

«Stop showing me the Social tab in my mail» is read as a hard interrupt by the grammar: before refactor2710-07 the turn
ended before the model and the mail order it carried was lost. Telling the two apart by the sentence's shape (a gerund,
«de» + infinitive, a token count) is a rule on his words (CRIT-W10); since refactor2710-07 the brief's `screen_action`
verdict decides it, asked before the turn and reused by it (`brief.verdict_before_the_turn`): a stop whose verdict
names a declared action on a card runs the turn; one that names nothing is still silence.

Disarm: make `hard_turn.names_an_act_on_screen` return False and the first test goes red.
"""
import asyncio

import pytest

from nucleo.flash import hard_turn
from nucleo.turn import brief
from voice.interrupt_grammar import hard_interrupt


def _verdict(monkeypatch, choice, used=True):
    async def _early(text, key, **_k):
        return (choice, {"used": used, "confidence": 0.9 if used else 0.3})
    monkeypatch.setattr(brief, "verdict_before_the_turn", _early)


def _handle(line):
    return asyncio.run(hard_turn.handle(line, hard_interrupt(line), lambda *a, **k: None))


@pytest.mark.parametrize("line", ["Stop showing me the Social tab in my mail",
                                  "Para de mostrarme los correos de la oficina"])
def test_a_stop_that_names_its_activity_runs_the_turn(monkeypatch, line):
    assert hard_interrupt(line) == "stop", "the grammar still hears a stop: the verdict, not its shape, decides"
    _verdict(monkeypatch, "mensajeria:mail_sort")
    assert _handle(line) == line


@pytest.mark.parametrize("choice,used", [("none", True), ("mensajeria:mail_sort", False), (None, False)])
def test_a_stop_the_verdict_does_not_aim_at_a_card_is_silence(monkeypatch, choice, used):
    _verdict(monkeypatch, choice, used)
    assert _handle("Stop showing me the Social tab in my mail") is None


@pytest.mark.parametrize("line", ["stop", "stop talking", "stop talking now", "para de hablar", "para de hablar ya",
                                  "silencio, por favor", "basta ya por favor"])
def test_a_bare_stop_is_still_silence(line):
    assert hard_interrupt(line) == "stop"
