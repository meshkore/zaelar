"""An everyday agenda edit follows the verdict (V2-781 T518, 2026-10-04).

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
    from nucleo.turn import brief as tb
    said = {tb.TARGET_KEY: "agenda:cancel_meeting", tb.REQUEST_KEY: "order"}

    def _read(b, k, d="", min_confidence=None):
        return (said[k], {"used": True}) if k in said else (d, None)
    monkeypatch.setattr(tb, "read", _read)
    from nucleo.flash import direct_action as da
    monkeypatch.setattr(da, "named_cards", lambda text: [])
    return said


@pytest.fixture
def model(monkeypatch):
    import nucleo.llm.fast_client as fc
    from nucleo.flash import widget_read
    monkeypatch.setattr(widget_read, "read", lambda wid, *a, **k: "Piano lesson with Abril · Tuesdays 17:00")

    def use(*rounds):
        m = _Model(*rounds)
        monkeypatch.setattr(fc, "FastClient", lambda: m)
        return m
    return use


def test_a_read_of_the_card_the_verdict_names_carries_the_op_out(brief):
    from nucleo.turn import brief as tb
    assert act_repair.same_card_order_after_read({"x": 1}, "agenda", "Let me check what's on the card.") == "cancel_meeting"
    brief[tb.REQUEST_KEY] = "question"
    assert act_repair.same_card_order_after_read({"x": 1}, "agenda") == "", "a question is answered by the read"
    brief[tb.REQUEST_KEY] = "comment"
    assert act_repair.same_card_order_after_read({"x": 1}, "agenda", "I'll cancel it.") == "", \
        "no sure order: our words decide nothing (refactor2710-03)"
    brief[tb.REQUEST_KEY] = "order"
    assert act_repair.same_card_order_after_read({"x": 1}, "mensajeria") == "", "another card is not this repair"
    brief[tb.TARGET_KEY], brief[tb.REQUEST_KEY] = "agenda:show_day", "comment"
    assert act_repair.same_card_order_after_read({"x": 1}, "agenda") == "", "a view verdict changes nothing"


def test_a_sure_order_for_a_lens_is_carried_out_after_the_read(brief):
    """Demo pass 124 (2026-10-14), F2: «go to the part about proof of work» — the verdict read `documento:goto` (1.00)
    and a sure ORDER; the model read the document and recited the section, and nothing moved on screen. A lens is
    still left to the words when the turn is no sure order (the test above); a sure order for one is the order."""
    from nucleo.turn import brief as tb
    brief[tb.TARGET_KEY], brief[tb.REQUEST_KEY] = "documento:goto", "order"
    assert act_repair.same_card_order_after_read({"x": 1}, "documento", "The relevant part is…") == "goto"
    brief[tb.REQUEST_KEY] = "comment"
    assert act_repair.same_card_order_after_read({"x": 1}, "documento", "The relevant part is…") == ""


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


# ── step 12: «What do I have next Thursday?» → «Done. Right now it holds: …» (every row on the card) ─────────

PARTE = {"executed": "widget_data", "widget": "agenda", "act": "show_day", "ops": [{"widget": "agenda", "act": "show_day"}],
         "answers": [("agenda", {"result": {"day": "2026-10-08", "meetings": [
             {"title": "Dental checkup with Dr Ruiz", "date": "2026-10-08", "startTime": "11:30"}]}})]}


def test_a_day_view_answers_with_that_days_rows_and_their_hours(tmp_path, monkeypatch):
    from widgets import store
    from widgets.agenda import data as agenda
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    agenda.apply_action("add_meeting", {"title": "Dental checkup", "date": "2026-10-08", "startTime": "11:30"})
    agenda.apply_action("add_meeting", {"title": "Piano", "date": "2026-10-07", "startTime": "17:00"})
    got = agenda.apply_action("show_day", {"day": "2026-10-08"})["result"]
    assert [m["title"] for m in got["meetings"]] == ["Dental checkup"] and got["meetings"][0]["startTime"] == "11:30"


def test_a_reply_that_holds_the_act_for_a_go_ahead_is_not_carried_out(brief):
    """A read of the card plus a reply that holds the act is never a licence to act — only a SURE order is (audit V2-783
    P0-3, 2026-10-16: «Shall I send it?» + a named recipient was sent by this repair)."""
    brief[__import__("nucleo.turn.brief", fromlist=["x"]).REQUEST_KEY] = "comment"
    assert act_repair.same_card_order_after_read({"x": 1}, "agenda", "Shall I cancel the piano on the 13th?") == ""
    brief[__import__("nucleo.turn.brief", fromlist=["x"]).REQUEST_KEY] = "order"
    assert act_repair.same_card_order_after_read({"x": 1}, "agenda", "Shall I cancel it?") == "cancel_meeting", \
        "a SURE order is carried out whatever the words — the operator's 70% decides, not the reply's shape"
