"""An order the card's data already meets is met — not «missing a detail», and not written twice (V2-831 T-19 pass 9).

Demo sandbox pass 9, INIT step 20: «Create a calendar event on November 6, 2026, from 4:00 PM to 5:00 PM titled
“Pixel — veterinarian”». The row was already in the agenda (an earlier step had put it there); the model said so and
called nothing; the second pass had only two answers — the write, or `cannot_do` — and declared a missing detail, so
he heard «I haven't done it yet — I'm missing a detail». The class: a repair's call is read against the data BEFORE it
runs — the action's declared end state, rendered over its payload (the same reading a write the card absorbed into a
row it held gets, T-19 R10). Met → nothing runs, the outcome is `held`, no honest line is owed. Any card, any order.
"""
import asyncio

import pytest

from nucleo.flash import act_repair
from nucleo.turn import promise_kept as pk
from widgets import rows

_PIXEL = {"title": "Pixel — veterinarian", "date": "2026-11-06", "startTime": "16:00", "endTime": "17:00"}


@pytest.fixture
def agenda(monkeypatch):
    held = [{"id": "m1", "title": "Pixel — veterinarian", "date": "2026-11-06", "startTime": "16:00"}]
    monkeypatch.setattr(rows, "_rows", lambda w, c: list(held) if (w, c) == ("agenda", "meetings") else [])
    events = []
    monkeypatch.setattr("voice.observer.emit", lambda kind, label, **k: events.append(k.get("extra") or {}))
    return events


def _pass(monkeypatch, payload):
    class _FC:                                # the second pass makes the write he ordered
        async def complete(self, messages, *, on_tool_call=None, **kw):
            on_tool_call("widget_data", {"widget_id": "agenda", "action": "add_meeting", "payload": dict(payload)})
            return ""
    import nucleo.llm.fast_client as fc
    monkeypatch.setattr(fc, "FastClient", _FC)
    outcome: dict = {}
    got = asyncio.new_event_loop().run_until_complete(act_repair.call_for_promise(
        "Create a calendar event on November 6, 2026, from 4:00 PM to 5:00 PM titled “Pixel — veterinarian”.",
        "That one's already on your calendar.", "agenda", outcome=outcome))
    return got, outcome


def test_a_write_the_data_already_meets_runs_nothing_and_owes_nothing(monkeypatch, agenda):
    got, outcome = _pass(monkeypatch, _PIXEL)
    assert got is None, "the order is met by the row it holds: nothing is written twice"
    assert outcome.get("kind") == pk.HELD
    assert pk.honest_line("That one's already on your calendar.", outcome, acted=False) == ""
    assert any(e.get("kind_diag") == "repair_already_held" for e in agenda)


def test_a_write_the_data_does_not_meet_still_runs(monkeypatch, agenda):
    got, outcome = _pass(monkeypatch, {**_PIXEL, "title": "Lunch with Laura", "date": "2026-11-02"})
    assert got and got["action"] == "add_meeting" and outcome.get("kind") == pk.CALL


def test_the_pass_is_told_a_held_order_is_still_called():
    assert "ALREADY HOLDS" in act_repair._SYS
