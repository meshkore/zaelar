"""«Close the widget video» is a CANVAS close, even though the video card declares an in-card action named `close`
(node 2.911).

Live, 2026-10-28 15:52 (T40–T48 of the operator's session): `screen_action = youtube:close` at 1.00 and `canvas = close`
at 0.87. `order_is_inside` read the action's name as «inside the card», the canvas close was ignored, the player was
unloaded instead, and the card stayed on screen through four more turns («I still see the YouTube widget»). An in-card
action that borrows the canvas verb's own name cannot, by itself, put the order inside the card: the canvas reader
leaning to close outvotes the alias. «Quita el vídeo» (canvas = neither) stays inside, and V2-770's agenda case is kept.

Disarm: with `_canvas_leans_close` answering False, the first test goes red.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import direct_action as card_verdict
from nucleo.turn import brief as _tb


def _brief(answers: dict, *, open_ids=("youtube",)):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids),
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


@pytest.fixture
def on_screen(monkeypatch):
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: True)


def test_close_the_widget_with_the_canvas_leaning_to_close_is_NOT_inside(on_screen):
    b = _brief({_tb.TARGET_KEY: ("youtube:close", 1.0), _tb.CANVAS_KEY: ("close", 0.87)})
    assert card_verdict.order_is_inside(b, "youtube") is False


def test_unload_the_video_with_no_canvas_close_stays_inside(on_screen):
    b = _brief({_tb.TARGET_KEY: ("youtube:close", 0.95), _tb.CANVAS_KEY: ("neither", 0.9)})
    assert card_verdict.order_is_inside(b, "youtube") is True


def test_an_action_that_merely_contains_close_is_still_inside(on_screen):
    """V2-770: «ya la puedes cerrar» over a detail card → `agenda:close_meeting`; the canvas may lean to close."""
    b = _brief({_tb.TARGET_KEY: ("agenda:close_meeting", 0.99), _tb.CANVAS_KEY: ("close", 0.6)}, open_ids=("agenda",))
    assert card_verdict.order_is_inside(b, "agenda") is True
