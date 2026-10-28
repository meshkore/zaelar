"""Node 2.494 — a row he named and took back («el último… no, el penúltimo») is not one of the rows of the order, so
the reorder is filled from the two rows that are left; a sentence that names three rows for real still fills nothing.

Use case `la-cola-de-video-con-palabras-imprecisas` (ES, 2026-10-11): «el último… no, el penúltimo, ponlo justo
después del de skills» read three rows (last, penultimate, skills), so `reorder_fill` had no order to fill. Since
refactor2710-07 WHICH row he took back is the brief's `item_ref` verdict over the rows on screen — no correction-word
table: the same sentence with no verdict names three rows and fills nothing.

Disarm: make `brief.withdrawn_rows` return an empty set and the corrected sentences fill nothing.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import payload_fill as _pf
from nucleo.turn import brief

from ._imprecise_queue_scene import QUEUE, SAID
from ._video_queue_scene import queue  # noqa: F401 — `queue` is a fixture


@pytest.fixture
def took_back(monkeypatch):
    def _set(row_id, conf=0.9):
        ev = threading.Event()
        ev.set()
        handle = {"event": ev, "result": {brief.ITEM_REF_KEY: {"choice": f"youtube#{row_id}", "confidence": conf}}}
        monkeypatch.setattr(brief, "of_this_turn", lambda: handle)
    return _set


def test_the_corrected_sentence_fills_the_move(queue, took_back):
    queue(QUEUE)
    took_back("5")
    assert _pf.reorder_fill("youtube", "move", SAID) == {"item": "4", "after": "1"}
    took_back("3")
    assert _pf.reorder_fill("youtube", "move", "the third one… sorry, I mean the second to last, after the skills one") \
        == {"item": "4", "after": "1"}


def test_a_corrected_anchor_is_the_one_that_counts(queue, took_back):
    queue(QUEUE)
    took_back("2")
    assert _pf.reorder_fill("youtube", "move", "the first before the second, no, the fourth") == {"item": "1", "before": "4"}


def test_without_a_sure_verdict_three_rows_are_still_no_order(queue, took_back):
    queue(QUEUE)
    assert _pf.reorder_fill("youtube", "move", "el último y el penúltimo después del de skills") == {}
    took_back("5", conf=0.3)
    assert _pf.reorder_fill("youtube", "move", SAID) == {}, "a shrug withdraws nothing"


def test_the_question_enumerates_the_rows_on_screen(queue):
    queue(QUEUE)
    q = brief.item_ref_question(["youtube"])
    assert set(q["criteria"]) == {f"youtube#{i}" for i in range(1, 6)} | {"none"}
    assert brief.item_ref_question([]) is None
    assert brief.ITEM_REF_KEY in brief.keys()
