"""A data-op that outlives the pool timeout is WORK IN PROGRESS: its future survives, the turn is told it is still
running, and the operator hears the widget's real answer when it ends (node 2.917).

Live, 2026-10-28 17:15: «quítalas todas» over 175 Google rows → «timed out after 8s» → the model said «the calendar
only lets me cancel them one at a time» while the rows kept disappearing for minutes. Nobody waited for the hook and
nobody reported what it finally did.

Disarm: with `wait_pending` returning None at once, the second test goes red.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from nucleo.flash import op_pending
from widgets import server_api


def test_a_timed_out_hook_keeps_its_future_and_its_answer_can_be_waited_for(monkeypatch):
    monkeypatch.setattr(server_api, "_TIMEOUT", 0.05)

    def slow(wid, fn, caller):
        time.sleep(0.3)
        return {"ok": True, "removed": 7}
    monkeypatch.setattr(server_api, "_call_widget", slow)

    async def run():
        res = await server_api._run_widget("agenda", "apply_action", lambda t: t())
        assert "timed out" in res["error"] and res.get("pending")
        return await server_api.wait_pending(res["pending"], timeout=2.0)
    assert asyncio.run(run()) == {"ok": True, "removed": 7}
    assert asyncio.run(server_api.wait_pending("nothing-here", timeout=0.1)) is None


@pytest.fixture
def mouth(monkeypatch):
    said, sealed = [], []
    from voice import proactive

    async def notify(title, text, **_k):
        said.append(text)
        return True
    monkeypatch.setattr(proactive, "notify", notify)
    from nucleo.flash import refusal_line
    monkeypatch.setattr(refusal_line, "speakable", lambda wid, res: "")
    return said, sealed


def test_when_it_ends_well_the_operator_hears_the_count(monkeypatch, mouth):
    said, sealed = mouth

    async def wait_pending(token, timeout=None):
        return {"ok": True, "removed": 175}
    monkeypatch.setattr(server_api, "wait_pending", wait_pending)
    res = asyncio.run(op_pending.still_running("agenda", "cancel_meeting", {"error": "timed out after 8s", "pending": "t"},
                                               seal=lambda ok: sealed.append(ok)))
    assert res == {"ok": True, "removed": 175} and sealed == [True]
    assert "175" in said[0]


def test_when_it_ends_badly_the_failure_is_said_once_and_nothing_is_claimed(monkeypatch, mouth):
    said, sealed = mouth

    async def wait_pending(token, timeout=None):
        return {"ok": False, "message": "Google no me dejó"}
    monkeypatch.setattr(server_api, "wait_pending", wait_pending)
    res = asyncio.run(op_pending.still_running("agenda", "cancel_meeting", {"error": "timed out after 8s", "pending": "t"},
                                               seal=lambda ok: sealed.append(ok)))
    # V2-851 F2: the late refusal is ONE line of the out-of-turn mouth — no correction note, no second voice
    assert res.get("ok") is False and sealed == [False] and len(said) == 1


def test_when_it_never_answers_nothing_is_claimed_either(monkeypatch, mouth):
    said, sealed = mouth

    async def wait_pending(token, timeout=None):
        return None
    monkeypatch.setattr(server_api, "wait_pending", wait_pending)
    res = asyncio.run(op_pending.still_running("agenda", "cancel_meeting", {"error": "timed out after 8s", "pending": "t"}))
    assert "timed out" in res["error"] and said == [] and sealed == []
