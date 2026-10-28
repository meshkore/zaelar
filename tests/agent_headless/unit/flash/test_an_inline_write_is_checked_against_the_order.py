"""An inline write is checked against the end state his words name, and completed once (demo pass 144, INIT).

«Save Quinn and Rowan in my contacts…» made ONE `add_contact`; the step said «Done.» and every later send to the
second person was refused. The turn now infers the order's end state, keeps only rows that must be present on the
card it wrote to, attests it, and lets one pass repeat ONLY an action this turn already ran there.
"""
import asyncio

import pytest

from nucleo.circuit import spec as _spec
from nucleo.circuit import compose as wh

GOAL = {"all": [{"widget": "contactos", "collection": "contacts", "where": {"title~": "Quinn"}, "expect": "present"},
                {"widget": "contactos", "collection": "contacts", "where": {"title~": "Rowan"}, "expect": "present"},
                {"widget": "agenda", "collection": "meetings", "where": {"title~": "Lunch"}, "expect": "present"},
                {"widget": "contactos", "collection": "contacts", "where": {"title~": "Old"}, "expect": "absent"}]}
ORDER = "Save Quinn and Rowan in my contacts: Quinn's Telegram is @quinn_q, and Rowan's email is rowan@example.com."


def test_the_goal_is_only_rows_that_must_be_present_on_the_card_written():
    goal = wh.goal_on(GOAL, "contactos", ORDER)
    assert [c["where"]["title~"] for c in goal["all"]] == ["Quinn", "Rowan"]
    assert wh.goal_on({"all": [{"widget": "documento", "field": "empty", "is": "false"}]}, "agenda", ORDER) is None


def test_a_row_his_words_never_named_is_never_owed():
    said = "Remember: the Tesla insurance renews on March 12, 2027; the vehicle registration renews in May 2027."
    inferred = {"all": [{"widget": "agenda", "collection": "meetings", "where": {"title~": "Tesla next service"}},
                        {"widget": "agenda", "collection": "meetings", "where": {"title~": "Ducati insurance renewal"}}]}
    assert wh.goal_on(inferred, "agenda", said) is None
    assert wh.goal_on({"all": [{"widget": "contactos", "collection": "contacts", "where": {"title~": "rowan"}}]},
                      "contactos", "guarda a Rowan en mis contactos")


def test_a_selector_that_names_no_row_is_nothing_to_check():
    """Demo sandbox 2026-10-28, C4 «actually move it half an hour later»: the inferred clause was `title~=""` — matched
    by no row, contained in every sentence — so the spec read unmet and the pass moved the meeting a second time."""
    empty = {"all": [{"widget": "agenda", "collection": "meetings", "where": {"title~": ""}, "expect": "present"}]}
    assert wh.goal_on(empty, "agenda", "actually move it half an hour later") is None
    assert wh.goal_on(empty, "agenda", "muévela media hora más tarde") is None
    named = {"all": [{"widget": "agenda", "collection": "meetings",
                      "where": {"title~": "Catch up with Rowan", "startTime": ""}, "expect": "present"}]}
    assert wh.goal_on(named, "agenda", "move catch up with rowan half an hour later")["all"] == named["all"]


def test_views_and_acts_that_leave_are_never_the_turns_writes():
    assert wh.writes_of([("contactos", "add_contact"), ("agenda", "show_day"), ("mensajeria", "send_to")]) == \
        [("contactos", "add_contact")]


@pytest.fixture
def world(monkeypatch):
    applied, verdicts = [], [False, True]

    async def infer(goal):
        return GOAL
    monkeypatch.setattr(_spec, "infer", infer)
    monkeypatch.setattr(_spec, "attest", lambda e, **k: verdicts.pop(0) if verdicts else True)

    class FakeClient:
        async def complete(self, messages, *, on_tool_call, **k):
            on_tool_call("widget_data", {"widget_id": "contactos", "action": "add_contact",
                                         "payload": {"name": "Rowan", "email": "rowan@example.com"}})
            on_tool_call("widget_data", {"widget_id": "contactos", "action": "remove_contact", "payload": {"name": "Quinn"}})
            on_tool_call("widget_data", {"widget_id": "agenda", "action": "add_meeting", "payload": {"title": "x"}})
    import nucleo.llm.fast_client as fc
    monkeypatch.setattr(fc, "FastClient", FakeClient)

    async def brain_action(wid, action, payload):
        applied.append((wid, action, payload))
        return {"ok": True}
    import widgets.server_api as sa
    monkeypatch.setattr(sa, "brain_action", brain_action)
    return applied


def test_what_the_order_named_and_the_turn_missed_is_added_with_an_action_it_already_ran(world):
    n = asyncio.run(wh.check(ORDER, [("contactos", "add_contact")], settle_s=0))
    assert n == 1 and world == [("contactos", "add_contact", {"name": "Rowan", "email": "rowan@example.com"})]


def test_a_met_end_state_calls_nothing(world, monkeypatch):
    monkeypatch.setattr(_spec, "attest", lambda e, **k: True)
    assert asyncio.run(wh.check(ORDER, [("contactos", "add_contact")], settle_s=0)) == 0 and world == []


def test_a_rows_name_is_read_where_the_collection_declares_its_label(monkeypatch):
    # the inferred goal says `title~`; contactos stores the name in `name` and declares `label: name`
    from widgets import rows
    monkeypatch.setattr(rows, "_rows", lambda w, c: [{"contactId": "c1", "name": "Quinn"}])
    assert rows.select("contactos", "contacts", {"title~": "quinn"}) and not rows.select("contactos", "contacts", {"title~": "rowan"})
    assert rows.relabel({"title|chatId~": "q", "date>=": "x"}, {"label": "name"}) == {"title|name|chatId~": "q", "date>=": "x"}
