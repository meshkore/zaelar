"""Node 2.453 — a question about HIS NAME is no missing detail: it must not keep the claimed-act repair from running.

Video-queue use case, regression sweep of 2026-10-11 (engine 3.36+2a5bd83c): «the third one before the second» (EN) —
verdict `youtube:move` 1.00, no call, «Done — Most Creative is now ahead of Los Goles» over an untouched queue; «cambia
el orden: el de skills ponlo antes que el de creative» (ES) — verdict split, a Brain Worker for ~100 s to swap two rows.
The green runs the day before were luck (the model happened to call `move {item: 2, to: 2}`).
"""
from __future__ import annotations

import pytest

from nucleo.flash import router as _router

from ._video_queue_scene import EN_CLAIM


@pytest.mark.parametrize("reply", [EN_CLAIM, "Hecho. Por cierto, ¿cómo te llamas?", "Done. What should I call you?"])
def test_a_name_question_keeps_the_repair_armed(reply):
    assert not _router.asks_for_missing_detail(reply)


@pytest.mark.parametrize("reply", ["¿A qué ciudad quieres ir?", "Which one do you mean?",
                                   "Done. Which video should go first, and what's your name?"])
def test_a_real_missing_detail_still_reads_as_one(reply):
    assert _router.asks_for_missing_detail(reply)
