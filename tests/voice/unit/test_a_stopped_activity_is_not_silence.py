"""A stop that names the ACTIVITY to stop is an order about it, not a silence order (bank case msg-en-mail-hide).

«Stop showing me the Social tab in my mail» was read as a hard interrupt: the turn ended before the model and the
mail order it carried was lost (the old text channel only named the stop after the model, so it never showed).
The stop verb followed, in its own clause, by a gerund or «de» + infinitive with a complement names a thing —
the same structure as a determiner after it (`_STOP_OBJECT_RE`). A bare «stop talking», «para de hablar», «silencio,
por favor» stays silence. Disarm: make `interrupt_grammar._stops_an_activity` return False → the first test is red.
"""
import pytest

from voice.interrupt_grammar import hard_interrupt


@pytest.mark.parametrize("line", ["Stop showing me the Social tab in my mail",
                                  "Para de mostrarme los correos de la oficina"])
def test_a_stop_that_names_its_activity_runs_the_turn(line):
    assert hard_interrupt(line) is None


@pytest.mark.parametrize("line", ["stop", "stop talking", "stop talking now", "para de hablar", "para de hablar ya",
                                  "silencio, por favor", "basta ya por favor"])
def test_a_bare_stop_is_still_silence(line):
    assert hard_interrupt(line) == "stop"
