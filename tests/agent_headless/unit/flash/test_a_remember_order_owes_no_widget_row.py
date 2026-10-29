"""A remember order owes no widget row on ANY opener, and the write harness keeps its real job (T-19 R6b).

Demo sandbox pass 2 at build 86+: «Remember these future responsibilities even when they are not on the calendar…».
The turn ran `add_reminder` (refused); the write harness inferred `agenda.meetings[title~=…]` ×3 — titles that ARE
in his words — repaired with `add_reminder` ×3, which can never make a meeting, and said the reminders were missing.
Two readers close it: the harness owes only rows of a collection one of the turn's own actions CREATES (`via.put`,
the manifest's datum), and a sure END «none» from the turn's brief stops the harness as it stops an errand's birth.
"""
import asyncio
import inspect

import pytest

from nucleo.circuit import compose as wh
from nucleo.circuit import spec as _spec

MEETINGS = {"all": [{"widget": "agenda", "collection": "meetings", "where": {"title~": "car insurance renewal"}},
                    {"widget": "agenda", "collection": "meetings", "where": {"title~": "registration renewal"}}]}
ORDERS = ["Remember these, even when they are not on the calendar: car insurance renewal on March 12, "
          "registration renewal in May",
          "Recuerda esto aunque no salga en el calendario: car insurance renewal el 12 de marzo, "
          "registration renewal en mayo"]


@pytest.mark.parametrize("order", ORDERS)
def test_a_write_that_cannot_create_the_row_owes_no_row(order):
    assert wh.goal_on(MEETINGS, "agenda", order) is not None            # the titles ARE in his words
    assert wh.goal_on(MEETINGS, "agenda", order, ["add_reminder"]) is None
    assert wh.goal_on(MEETINGS, "agenda", order, ["add_reminder", "add_meeting"])["all"] == MEETINGS["all"]


@pytest.mark.parametrize("order", ORDERS)
def test_the_harness_never_repairs_a_remember_order_into_rows(monkeypatch, order):
    async def infer(goal):
        return MEETINGS
    monkeypatch.setattr(_spec, "infer", infer)
    applied = []

    async def brain_action(wid, action, payload):
        applied.append(action)
        return {"ok": True}
    import widgets.server_api as sa
    monkeypatch.setattr(sa, "brain_action", brain_action)
    assert asyncio.run(wh.check(order, [("agenda", "add_reminder")], settle_s=0)) == 0 and applied == []


def test_two_contacts_where_the_turn_wrote_one_are_still_completed(monkeypatch):
    """The harness's real job survives: `add_contact` creates contacts, so the second one is still owed."""
    goal = {"all": [{"widget": "contactos", "collection": "contacts", "where": {"title~": "Quinn"}},
                    {"widget": "contactos", "collection": "contacts", "where": {"title~": "Rowan"}}]}

    async def infer(g):
        return goal
    monkeypatch.setattr(_spec, "infer", infer)
    verdicts = [False, True]
    monkeypatch.setattr(_spec, "attest", lambda e, **k: verdicts.pop(0) if verdicts else True)

    class FakeClient:
        async def complete(self, messages, *, on_tool_call, **k):
            on_tool_call("widget_data", {"widget_id": "contactos", "action": "add_contact", "payload": {"name": "Rowan"}})
    import nucleo.llm.fast_client as fc
    monkeypatch.setattr(fc, "FastClient", FakeClient)
    applied = []

    async def brain_action(wid, action, payload):
        applied.append((action, payload))
        return {"ok": True}
    import widgets.server_api as sa
    monkeypatch.setattr(sa, "brain_action", brain_action)
    n = asyncio.run(wh.check("Save Quinn and Rowan in my contacts", [("contactos", "add_contact")], settle_s=0))
    assert n == 1 and applied == [("add_contact", {"name": "Rowan"})]


@pytest.mark.parametrize("order", ORDERS)
def test_a_sure_end_none_schedules_no_harness(monkeypatch, order):
    from nucleo.turn import brief as _tb
    scheduled = []

    async def check(*a, **k):
        scheduled.append(a)
        return 0
    monkeypatch.setattr(wh, "check", check)

    async def go(answer):
        monkeypatch.setattr(_tb, "read", lambda h, k, fb, **kw: answer)
        wh.after_turn(order, [("agenda", "add_reminder")], brief={"x": 1})
        await asyncio.sleep(0)
    asyncio.run(go(("none", {"used": True})))
    assert scheduled == []
    asyncio.run(go(("", {"used": False, "choice": "none"})))           # unsure: the harness still looks
    assert len(scheduled) == 1


def test_the_turn_hands_its_brief_to_the_harness():
    from nucleo.flash import post_stream
    assert '.after_turn(operator_text, data_done.get("ops"), spec=spec, brief=_brief)' in inspect.getsource(post_stream)
