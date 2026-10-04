"""An everyday agenda edit follows the verdict, in both channels (V2-781 T518, 2026-10-04).

Measured on the EN pair `agenda-everyday-edits__us` (ES 13/13 on the same code):
  · «And make it last until one» — verdict `agenda:move_meeting` 0.98; the promise repair read «I'll open it so
    you can see it» and synthesised `open_meeting`. A view the repair picks over a real op the verdict names is
    asked once more, for that op (CRIT-K2: the verdict completes the model).
  · «There's no piano on Tuesday October 13» — verdict `agenda:cancel_meeting` 1.00, brief `request_type=comment`;
    the model said «let me check», READ the agenda and the read's tool-less answer said «Got it — no piano on the
    13th» over a series that still held it. A read of the very card a sure verdict names, after the model itself
    promised to act, carries the op out. The text channel had no read-for-an-order repair at all.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import act_repair

MOVE = ("widget_data", {"widget_id": "agenda", "action": "move_meeting",
                        "payload": {"title": "Dental checkup", "endTime": "13:00"}})
CANCEL = ("widget_data", {"widget_id": "agenda", "action": "cancel_meeting",
                          "payload": {"title": "Piano lesson with Abril", "date": "2026-10-13"}})


class _Model:
    def __init__(self, *rounds):
        self.rounds, self.n = list(rounds), 0

    async def complete(self, messages, **kw):
        calls = self.rounds[self.n] if self.n < len(self.rounds) else []
        self.n += 1
        for name, args in calls:
            kw["on_tool_call"](name, args)


@pytest.fixture
def brief(monkeypatch):
    from nucleo.flash import reply_promise as rp, turn_brief as tb
    said = {tb.TARGET_KEY: "agenda:cancel_meeting", tb.REQUEST_KEY: "comment", "promise": "act"}

    def _read(b, k, d="", min_confidence=None):
        return (said[k], {"used": True}) if k in said else (d, None)
    monkeypatch.setattr(tb, "read", _read)
    monkeypatch.setattr(rp, "verdict", lambda reply: said["promise"])
    from nucleo.flash import direct_action as da
    monkeypatch.setattr(da, "named_cards", lambda text: [])
    return said


@pytest.fixture
def model(monkeypatch):
    import nucleo.flash.fast_client as fc
    from nucleo.flash import widget_read
    monkeypatch.setattr(widget_read, "read", lambda wid, *a, **k: "Piano lesson with Abril · Tuesdays 17:00")

    def use(*rounds):
        m = _Model(*rounds)
        monkeypatch.setattr(fc, "FastClient", lambda: m)
        return m
    return use


def test_a_read_of_the_card_the_verdict_names_carries_the_op_out(brief):
    from nucleo.flash import turn_brief as tb
    assert act_repair.same_card_order_after_read({"x": 1}, "agenda", "Let me check what's on the card.") == "cancel_meeting"
    brief[tb.REQUEST_KEY] = "question"
    assert act_repair.same_card_order_after_read({"x": 1}, "agenda") == "", "a question is answered by the read"
    brief[tb.REQUEST_KEY], brief["promise"] = "comment", "none"
    assert act_repair.same_card_order_after_read({"x": 1}, "agenda") == "", "no promise and no sure order: words"
    brief["promise"] = "act"
    assert act_repair.same_card_order_after_read({"x": 1}, "mensajeria") == "", "another card is not this repair"
    brief[tb.TARGET_KEY] = "agenda:show_day"
    assert act_repair.same_card_order_after_read({"x": 1}, "agenda") == "", "a view verdict changes nothing"


def test_the_probe_read_route_runs_the_op_instead_of_answering_in_words(brief, model):
    from nucleo.flash import second_pass
    m = model([CANCEL])
    calls = [{"name": "read_widget", "args": {"widget_id": "agenda", "question": "piano occurrences"}}]
    spoken, action = asyncio.run(second_pass.probe_light_routes(
        "read_widget", ["read_widget"], calls, "There's no piano on Tuesday October 13",
        "There's no piano on Tuesday October 13", None, lambda s: s, brief={"x": 1}, reply="Let me check."))
    assert (spoken, action) == ("", "widget_data") and m.n == 1
    assert calls[-1]["args"]["action"] == "cancel_meeting" and calls[-1]["args"]["_repair"] is True


def test_a_view_the_promise_pass_picks_yields_to_the_verdicts_op(model, monkeypatch):
    from widgets import runtime as rt
    real = rt.get

    def _get(wid):
        return real("agenda") if wid == "agenda" else real(wid)
    monkeypatch.setattr(rt, "get", _get)
    open_call = ("widget_data", {"widget_id": "agenda", "action": "open_meeting", "payload": {"title": "Dental checkup"}})
    m = model([open_call], [MOVE])
    got = asyncio.run(act_repair.call_for_promise_or_order(
        "And make it last until one", "I'll open it so you can see it.", "agenda", "move_meeting"))
    assert got and got["action"] == "move_meeting" and m.n == 2, got


def test_a_view_the_verdict_also_names_is_left_alone(model):
    open_call = ("widget_data", {"widget_id": "agenda", "action": "open_meeting", "payload": {"title": "Dental checkup"}})
    m = model([open_call])
    got = asyncio.run(act_repair.call_for_promise_or_order(
        "Open the dentist", "I'll open it so you can see it.", "agenda", "open_meeting"))
    assert got["action"] == "open_meeting" and m.n == 1


def test_the_voice_read_lane_uses_the_same_door():
    import inspect
    from nucleo.flash import post_stream_lanes
    src = inspect.getsource(post_stream_lanes)
    assert "_act_repair.after_a_read(" in src and "order_card_after_read" not in src
