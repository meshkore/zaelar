"""A stop that names the ACTIVITY to stop is an order about it, not a silence order (bank case msg-en-mail-hide).

«Stop showing me the Social tab in my mail» is read as a hard interrupt: the turn ends before the model and the mail
order it carried is lost. Telling the two apart by the sentence's shape (a gerund, «de» + infinitive, a token count)
is a rule on his words (CRIT-W10); it is decided by a verdict (`stop_errand` / `end_state` in Jev's brief), which the
07 brings. Until then the first test is an expected failure, strict.
"""
import pytest

from voice.interrupt_grammar import hard_interrupt


@pytest.mark.xfail(reason="refactor2710-07: a stop is a brief verdict", strict=True)
@pytest.mark.parametrize("line", ["Stop showing me the Social tab in my mail",
                                  "Para de mostrarme los correos de la oficina"])
def test_a_stop_that_names_its_activity_runs_the_turn(line):
    assert hard_interrupt(line) is None


@pytest.mark.parametrize("line", ["stop", "stop talking", "stop talking now", "para de hablar", "para de hablar ya",
                                  "silencio, por favor", "basta ya por favor"])
def test_a_bare_stop_is_still_silence(line):
    assert hard_interrupt(line) == "stop"
