"""A question never gets a WRITE from the show repair (demo pass 134, 2026-10-15, R2).

«and when does anna's vacation start? show me in the calendar» — the verdict read a QUESTION; the model opened the
agenda and promised more, and the «opened the card and promised more» repair added «Anna's vacation» as a meeting
nobody had asked to create. The repair may still run a VIEW on a question, and anything on an order.
"""
import asyncio
import threading

import pytest

from nucleo.flash import act_repair as AR
from nucleo.flash import card_commission as CC


def _brief(kind: str) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": ["agenda"], "_call_id": "t",
            "result": {"request_type": {"choice": kind, "confidence": 1.0},
                       "screen_action": {"choice": "agenda:show_day", "confidence": 0.9}}}


def _run(monkeypatch, kind: str, repaired: dict) -> list:
    async def call_for_promise(*a, **k):
        return repaired
    monkeypatch.setattr(AR, "call_for_promise", call_for_promise)
    ran: list = []
    asyncio.run(CC.after_show({"widget_id": "agenda"}, brief=_brief(kind),
                              operator_text="and when does anna's vacation start? show me in the calendar",
                              spoken_text="Anna's vacation starts December 20 — let me pull it up on your calendar.",
                              spec=None, emit=lambda *a, **k: None, present=lambda *a, **k: None,
                              apply_widget_data=lambda w, a, p: ran.append((w, a))))
    return ran


def test_a_question_does_not_create_a_meeting(monkeypatch):
    write = {"widget_id": "agenda", "action": "add_meeting", "payload": {"title": "Anna's vacation", "date": "2026-12-20"}}
    assert _run(monkeypatch, "question", write) == []


def test_a_question_may_still_move_the_view(monkeypatch):
    view = {"widget_id": "agenda", "action": "show_day", "payload": {"day": "2026-12-20"}}
    assert _run(monkeypatch, "question", view) == [("agenda", "show_day")]


def test_an_order_keeps_its_write(monkeypatch):
    write = {"widget_id": "agenda", "action": "add_meeting", "payload": {"title": "Anna's vacation", "date": "2026-12-20"}}
    assert _run(monkeypatch, "order", write) == [("agenda", "add_meeting")]
