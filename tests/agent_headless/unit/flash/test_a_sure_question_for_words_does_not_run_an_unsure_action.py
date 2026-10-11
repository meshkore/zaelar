"""A turn the verdict SURELY reads as «tell me» gets no UNSURE action completed into it (2026-10-11).

`build-a-video-playlist-from-links__us`, turn 4: «did you actually skip it? what's playing now» — `wants_words = tell`
1.00, `request_type = question` 0.99, `screen_action = youtube:next` 0.54. The completion ran a second `youtube:next`
over the last item and the reply became «I couldn't: There are no more videos in the list.», which the model then
believed for two turns. The queue digest was right the whole time — the poison was our own false report.

`question` alone is NOT a veto (V2-757: «¿Me pones el siguiente?» reads `next` 0.75 and is an order). The words
reader tells the two apart: a polite order answers `act`; and a SURE action runs whatever the words reader says.

Disarm: with `tell_vetoes_unsure_action` returning False the first test goes red.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import direct_action as DA
from nucleo.flash import words_only as WO


def _brief(*, screen="youtube:next", screen_conf=0.54, words="tell", words_conf=1.0, kind="question", kind_conf=0.99):
    ev = threading.Event()
    ev.set()
    res = {"request_type": {"choice": kind, "confidence": kind_conf}}
    if screen:
        res["screen_action"] = {"choice": screen, "confidence": screen_conf}
    if words:
        res["wants_words"] = {"choice": words, "confidence": words_conf}
    return {"event": ev, "turn_id": "t-1", "open_ids": ["youtube"], "result": res}


@pytest.fixture(autouse=True)
def _screen(monkeypatch):
    from memory import api as _memapi
    monkeypatch.setattr(_memapi, "state", lambda *a, **k: {"open_widgets": ["youtube"]})


def test_a_sure_tell_over_an_unsure_action_is_no_order():
    b = _brief()
    assert WO.tell_vetoes_unsure_action(b)
    assert not DA.names_an_order(b)


def test_a_polite_order_shaped_like_a_question_still_runs():
    """«¿Me pones el siguiente?» — question-shaped, but the words reader says `act`."""
    b = _brief(words="act", words_conf=0.95, screen_conf=0.75)
    assert not WO.tell_vetoes_unsure_action(b)
    assert DA.names_an_order(b)


def test_a_sure_action_runs_whatever_the_words_reader_says():
    """«¿Puedes parar el vídeo?» — `pause` 1.00: a sure action is never vetoed by the words reader."""
    b = _brief(screen="youtube:pause", screen_conf=1.0)
    assert not WO.tell_vetoes_unsure_action(b)
    assert DA.names_an_order(b)


def test_an_unsure_tell_vetoes_nothing():
    b = _brief(words_conf=0.6)
    assert not WO.tell_vetoes_unsure_action(b)
    assert DA.names_an_order(b)
    assert not WO.tell_vetoes_unsure_action(_brief(words=None)), "no words verdict → today's path"
    assert not WO.tell_vetoes_unsure_action(None)
