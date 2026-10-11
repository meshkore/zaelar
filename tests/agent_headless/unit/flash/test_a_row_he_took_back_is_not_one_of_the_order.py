"""Node 2.494 — a row he named and took back («el último… no, el penúltimo») is not one of the rows of the order, so
the reorder is filled from the two rows that are left; a sentence that names three rows for real still fills nothing.

Use case `la-cola-de-video-con-palabras-imprecisas` (ES, 2026-10-11): «el último… no, el penúltimo, ponlo justo
después del de skills» read three rows (last, penultimate, skills), so `reorder_fill` had no order to fill.
"""
from __future__ import annotations

from nucleo.flash import payload_fill as _pf
from nucleo.flash import said_positions as SP
from widgets import refs

from ._imprecise_queue_scene import QUEUE, SAID
from ._video_queue_scene import queue  # noqa: F401 — `queue` is a fixture


def test_the_corrected_sentence_fills_the_move(queue):
    queue(QUEUE)
    assert _pf.reorder_fill("youtube", "move", SAID) == {"item": "4", "after": "1"}
    assert _pf.reorder_fill("youtube", "move", "the third one… sorry, I mean the second to last, after the skills one") \
        == {"item": "4", "after": "1"}


def test_a_corrected_anchor_is_the_one_that_counts(queue):
    queue(QUEUE)
    assert _pf.reorder_fill("youtube", "move", "the first before the second, no, the fourth") == {"item": "1", "before": "4"}


def test_three_rows_said_for_real_are_still_no_order(queue):
    queue(QUEUE)
    assert _pf.reorder_fill("youtube", "move", "el último y el penúltimo después del de skills") == {}


def test_only_a_bare_correction_withdraws_a_row():
    norm = refs._norm("el ultimo no el penultimo")
    assert SP.drop_retracted([(3, 5), (16, 4)], norm) == [(16, 4)]
    norm = refs._norm("el ultimo antes que el penultimo")
    assert SP.drop_retracted([(3, 5), (23, 4)], norm) == [(3, 5), (23, 4)]
