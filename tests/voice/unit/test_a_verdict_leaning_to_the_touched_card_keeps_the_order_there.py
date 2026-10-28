"""A verdict that LEANS to the card the turn touched is evidence that there is no other card: the second pass «the
order was on another card» does not fire on a grammar match against it (node 2.912).

Live, 2026-10-28 15:48 (T14): «Okay. Show me a message for, uh, show me a video from SpaceX right now.» — the brief read
`screen_action = youtube:search` at 0.73 and `request_type = order` at 0.89; the turn loaded a video on the video card.
The old floor (0.8) discarded the 0.73, the grammar found «message» in the retracted half, and a second pass opened the
messages card he had not asked for. The target is read at the licence floor: a guard of words cannot refute a verdict.

Disarm: reading the target at 0.8 again turns the first test red.
"""
from __future__ import annotations

import threading

from nucleo.flash import direct_action as card_verdict
canvas_verdict = card_verdict
from nucleo.turn import brief as _tb

SAID = "Okay. Show me a message for, uh, show me a video from SpaceX right now."


def _brief(answers: dict):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": ["youtube"],
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


def test_a_verdict_at_0_73_on_the_touched_card_keeps_the_order_there(monkeypatch):
    monkeypatch.setattr(canvas_verdict, "named_cards", lambda _t: ["mensajeria"])
    b = _brief({_tb.REQUEST_KEY: ("order", 0.89), _tb.TARGET_KEY: ("youtube:search", 0.73)})
    assert card_verdict.order_card_after_read(b, SAID, "youtube") == ""


def test_with_no_target_verdict_the_named_other_card_still_wins(monkeypatch):
    """The second pass itself is kept (full23 C5: the order on the messages card while the agenda was touched)."""
    monkeypatch.setattr(canvas_verdict, "named_cards", lambda _t: ["mensajeria"])
    b = _brief({_tb.REQUEST_KEY: ("order", 0.89)})
    assert card_verdict.order_card_after_read(b, "send rowan a telegram with the new time", "agenda") == "mensajeria"


def test_a_verdict_on_a_THIRD_card_does_not_block_the_named_one(monkeypatch):
    monkeypatch.setattr(canvas_verdict, "named_cards", lambda _t: ["mensajeria"])
    b = _brief({_tb.REQUEST_KEY: ("order", 0.89), _tb.TARGET_KEY: ("agenda:add_meeting", 0.6)})
    assert card_verdict.order_card_after_read(b, "send rowan a telegram", "youtube") == "mensajeria"
