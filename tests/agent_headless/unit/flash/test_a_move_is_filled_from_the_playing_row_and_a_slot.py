"""Node 2.461 — a move is filled from the row that is PLAYING (the card's own hint) and the slot he named, in both
languages; one half alone, or no verb behind a clause-final ordinal, fills nothing.

Video-queue use case, ES round of 2026-10-11 (engine 3.36+d6f4a99f): «El que está sonando ahora, ese ponlo el primero»
— verdict `youtube:move` 0.97 and no reading could fill it (`reorder_fill` wants two rows, `number_fill` one bare index);
two turns later he had translated it himself: «Es el 2 ahora mismo, ponlo el 1».
"""
from __future__ import annotations

import pytest

from nucleo.flash import move_fill as _mf
from nucleo.flash import payload_fill as _pf

from ._video_queue_scene import queue  # noqa: F401 — a fixture

ES_QUEUE = ["Diego Maradona 👑 Prime Argentina Skills, Goals, Dribbling & Tricks",
            "Opus - Live Is Life | Maradona Calentamiento 1989", "Los Goles Inolvidables de Diego Maradona",
            "Maradona - Anubiis x Hades 66 x  (Video Oficial)"]
ES_SAID = "El que está sonando ahora, ese ponlo el primero, que me gusta más que los otros."


@pytest.mark.parametrize("said, expected", [
    (ES_SAID, {"item": "4", "to": 1}),
    ("put the one that's playing first", {"item": "4", "to": 1}),
    ("move the one playing to the top", {"item": "4", "to": 1}),
    ("the one playing, put it at the end", {"item": "4", "to": 4}),
    ("Es el 2 ahora mismo, ponlo el 1.", {"item": "2", "to": 1}),       # a row he numbered, and a slot
    ("move number 3 to position 2", {"item": "3", "to": 2}),
])
def test_the_playing_row_or_a_numbered_row_and_the_slot_he_said(queue, said, expected):
    queue(ES_QUEUE, pos=3)
    assert _mf.move_fill("youtube", "move", said) == expected
    assert _pf.choice_or_order_fill("youtube", "move", said, "") == (expected, "said-move")


@pytest.mark.parametrize("said", [
    "ponlo el último",                             # a slot and no row — with nothing parked, a question
    "move it",
    "Move the third one before the second",        # the reorder's shape: no slot said
    "A la 1, ponlo el primero de todos.",          # a slot alone, nothing parked
    "the one playing is great, first class",       # an ordinal with no verb behind it is not a destination
    "put the one playing first, no, last",         # two slots: not one order
])
def test_one_half_alone_or_an_ambiguous_slot_fills_nothing(queue, said):
    queue(ES_QUEUE, pos=3)
    assert _mf.move_fill("youtube", "move", said) == {}


def test_nothing_is_playing_so_the_playing_row_names_nothing(queue):
    queue(ES_QUEUE, pos=-1)
    assert _mf.move_fill("youtube", "move", ES_SAID) == {}


def test_an_action_without_a_slot_key_is_never_filled(queue):
    queue(ES_QUEUE, pos=3)
    assert _mf.move_fill("youtube", "play_item", "put the one playing first") == {}
    assert _mf.move_fill("youtube", "remove", "quita el que está sonando, el primero") == {}
