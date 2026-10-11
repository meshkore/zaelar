"""Node 2.451 — the two rows his words (or the model's own claim) name fill a reorder, with the side said between them.

Video-queue use case, regression sweep of 2026-10-11 (engine 3.36+2a5bd83c): «the third one before the second» (EN) —
verdict `youtube:move` 1.00, no call, «Done — Most Creative is now ahead of Los Goles» over an untouched queue; «cambia
el orden: el de skills ponlo antes que el de creative» (ES) — verdict split, a Brain Worker for ~100 s to swap two rows.
The green runs the day before were luck (the model happened to call `move {item: 2, to: 2}`).
"""
from __future__ import annotations

import pytest

from nucleo.flash import payload_fill as _pf

from ._video_queue_scene import EN_CLAIM, EN_QUEUE, EN_SAID, ES_QUEUE, ES_SAID, queue  # noqa: F401


def test_two_spoken_positions_and_the_side_between_them(queue):
    queue(EN_QUEUE)
    assert _pf.reorder_fill("youtube", "move", EN_SAID) == {"item": "3", "before": "2"}


def test_a_word_only_one_title_carries_names_that_row(queue):
    queue(ES_QUEUE)
    assert _pf.reorder_fill("youtube", "move", ES_SAID) == {"item": "1", "before": "2"}
    assert _pf.reorder_fill("youtube", "move", "pon el de creative detrás del de skills") == {"item": "2", "after": "1"}


def test_the_models_claim_names_the_same_two_rows_when_his_words_do_not(queue):
    queue(EN_QUEUE)
    assert _pf.reorder_fill("youtube", "move", "do that swap", EN_CLAIM) == {"item": "3", "before": "2"}


@pytest.mark.parametrize("said", [
    "swap the third and the second",                 # no side said: a question, never a guess
    "put the Maradona one before the Maradona one",  # a word every row carries names nothing
    "the first before the second and the fourth",    # three rows: not one order («…, no, the fourth» is a
                                                     # correction — node 2.494 — and fills first-before-fourth)
    "move it",
])
def test_no_fill_without_two_rows_and_a_side(queue, said):
    queue(EN_QUEUE)
    assert _pf.reorder_fill("youtube", "move", said) == {}


def test_an_action_without_an_anchor_key_is_never_filled(queue):
    queue(EN_QUEUE)
    assert _pf.reorder_fill("youtube", "play_item", EN_SAID) == {}
