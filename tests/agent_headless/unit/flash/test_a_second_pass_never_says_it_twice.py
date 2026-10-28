"""A second pass never says again what the turn already said (demo pass 144, E1, 2026-10-19).

«Yep — they did, there's an Inworld message in your inbox. Yep — they did, there's an Inworld message in your inbox.»
The op-answer pass was asked to answer SKIP when the words already said answered; it repeated them verbatim and the
voice spoke both. The engine now holds a pass while it only repeats, word for word, what was said — a pass that ends
held is never spoken — and releases it the moment it says something new.
"""

from nucleo.flash.second_pass import still_held

SAID = "Yep — they did, there's an Inworld message in your inbox."


def test_a_verbatim_repeat_is_held_to_the_end():
    for upto in (3, 12, 30, len(SAID)):
        assert still_held(SAID[:upto], SAID), SAID[:upto]


def test_the_same_in_spanish():
    dicho = "Sí, te escribieron ayer: un recibo de 25 dólares."
    assert still_held(dicho, dicho) and not still_held("Sí, te escribieron ayer y hoy otra vez", dicho)


def test_something_new_is_released_at_once():
    assert not still_held("Yep — they did, it was a receipt", SAID)
    assert not still_held("It was a receipt for $25", SAID)


def test_a_short_answer_that_only_shares_letters_is_not_a_repeat():
    assert not still_held("No.", "Nothing from them yet.")
