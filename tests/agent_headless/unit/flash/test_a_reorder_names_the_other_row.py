"""Node 2.450 — the queue's `move` takes the OTHER row («put X before Y»); the widget does the slot arithmetic.

Video-queue use case, regression sweep of 2026-10-11 (engine 3.36+2a5bd83c): «the third one before the second» (EN) —
verdict `youtube:move` 1.00, no call, «Done — Most Creative is now ahead of Los Goles» over an untouched queue; «cambia
el orden: el de skills ponlo antes que el de creative» (ES) — verdict split, a Brain Worker for ~100 s to swap two rows.
The green runs the day before were luck (the model happened to call `move {item: 2, to: 2}`).
"""
from __future__ import annotations

from widgets.youtube import data as yt

from ._video_queue_scene import EN_QUEUE, ES_QUEUE, queue, titles  # noqa: F401 — `queue` is a fixture


def test_before_puts_the_item_right_ahead_of_the_other_row(queue):
    queue(EN_QUEUE, pos=1)
    r = yt.apply_action("move", {"item": "3", "before": "2"})
    assert r["ok"], r
    assert titles() == [EN_QUEUE[0], EN_QUEUE[2], EN_QUEUE[1], EN_QUEUE[3]]
    assert yt._load()["pos"] == 2                                    # the playing video keeps playing


def test_after_and_titles_resolve_like_item(queue):
    queue(ES_QUEUE)
    assert yt.apply_action("move", {"item": "skills", "after": "creative"})["ok"]
    assert titles() == [ES_QUEUE[1], ES_QUEUE[0], ES_QUEUE[2]]
    assert yt.apply_action("move", {"item": "1", "before": "20 mejores"})["ok"]     # forward: slot counted after pop
    assert titles() == [ES_QUEUE[0], ES_QUEUE[1], ES_QUEUE[2]]


def test_a_slot_still_works_and_nonsense_is_refused(queue):
    queue(EN_QUEUE)
    assert yt.apply_action("move", {"item": "4", "to": "1"})["ok"]
    assert titles()[0] == EN_QUEUE[3]
    assert yt.apply_action("move", {"item": "1", "before": "1"})["error"] == "same_item"
    assert yt.apply_action("move", {"item": "1", "before": "no such video"})["error"] == "item_not_found"
