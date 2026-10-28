"""An answer that promised nothing is never repaired into an act (V2-781 T529, pair 16).

«and the day after the dinner, do I have anything?» → «The day after the dinner is Friday the 16th, and you've got
nothing on it.» — right, and `reply_promise=none (1.00)`. The promise repair ran anyway (the catalogue named the
agenda), made `show_day`, blanked the answer and spoke «Done. Right now it holds: …». A repair is for an act the
brief says was owed, or a refusal of an act the card declares — never for a question the brief is sure of
(refactor2710-03: the brief decides, not our words).
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import act_repair as A


@pytest.fixture
def spy(monkeypatch):
    calls = []

    async def _cfp(*a, **k):
        calls.append(a)
        return {"widget_id": "agenda", "action": "show_day", "payload": {"day": "2026-10-16"}}
    monkeypatch.setattr(A, "call_for_promise", _cfp)
    return calls


def _run(reply, kind="question"):
    import unittest.mock as m
    from nucleo.turn import brief as TB
    with m.patch.object(TB, "read", lambda b, key, d="", **k: (kind, {"confidence": 1.0})):
        return asyncio.run(A.call_for_promise_or_order("do I have anything on the 16th?", reply, "agenda",
                                                       brief=object()))


def test_a_sure_question_is_left_as_it_was_whatever_the_words(spy):
    assert _run("The 16th is free, you've got nothing on it.") is None and spy == []
    assert _run("I'll pull up that day.") is None and spy == []


def test_a_refusal_still_reaches_the_verdict(spy):
    assert _run("I can't send it myself.")


def test_an_order_is_repaired(spy):
    assert _run("Hecho.", kind="order")
    assert _run("I'll pull up that day.", kind="order")
