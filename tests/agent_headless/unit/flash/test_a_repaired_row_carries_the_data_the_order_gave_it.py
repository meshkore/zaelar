"""A row the write harness completes carries the data the order gave it, and a bare row does not attest (T-19 R2).

Demo sandbox at build 86, INIT: «Save <a> and <b>… <b>'s email is …» made ONE create; the harness completed the
second with `{"name": <b>, "kind": "person"}` — no address — and the inferred end state, which only asked for a row
NAMED <b>, read «met». The class: a clause names the row (`where`) and carries what the order stated for it
(`with`); the repair's payload is grounded in that, for any card's create action, and the verifier reads it.
"""
import asyncio

import pytest

from nucleo.circuit import compose as wh
from nucleo.circuit import spec as _spec
from nucleo.circuit import verify as _verify
from widgets import rows


def _contacts_goal():
    return {"all": [
        {"widget": "contactos", "collection": "contacts", "where": {"title~": "Quinn"}, "expect": "present"},
        {"widget": "contactos", "collection": "contacts", "where": {"title~": "Rowan"},
         "with": {"email": "rowan@example.com"}, "expect": "present"}]}


def _tasks_goal():
    return {"all": [
        {"widget": "agenda", "collection": "tasks", "where": {"title~": "comprar papel"}, "with": {"list": "casa"}},
        {"widget": "agenda", "collection": "tasks", "where": {"title~": "llamar a rowan"}, "with": {"list": "trabajo"}}]}


@pytest.fixture
def store(monkeypatch):
    """An in-memory card: the turn's own write is already there; the repair's writes land in it."""
    data: dict = {("contactos", "contacts"): [{"contactId": "c1", "name": "Quinn"}],
                  ("agenda", "tasks"): [{"id": "t1", "title": "Comprar papel", "list": "casa"}]}
    monkeypatch.setattr(rows, "_rows", lambda w, c: list(data.get((w, c), [])))
    applied: list = []

    async def brain_action(wid, action, payload):
        applied.append((wid, action, payload))
        coll = {"contactos": "contacts", "agenda": "tasks"}[wid]
        data.setdefault((wid, coll), []).append(dict(payload))
        return {"ok": True}
    import widgets.server_api as sa
    monkeypatch.setattr(sa, "brain_action", brain_action)
    _spec.reset()
    yield applied
    _spec.reset()


def _repair_writes(monkeypatch, goal, card, action, bare):
    async def infer(order):
        return goal
    monkeypatch.setattr(_spec, "infer", infer)

    class FakeClient:                       # the repair model names the row and drops its data
        async def complete(self, messages, *, on_tool_call, **k):
            on_tool_call("widget_data", {"widget_id": card, "action": action, "payload": dict(bare)})
    import nucleo.llm.fast_client as fc
    monkeypatch.setattr(fc, "FastClient", FakeClient)


def test_the_repair_writes_the_second_contact_with_the_email_the_order_gave_it(store, monkeypatch):
    order = "Save Quinn and Rowan in my contacts. Rowan's email is rowan@example.com."
    _repair_writes(monkeypatch, _contacts_goal(), "contactos", "add_contact", {"name": "Rowan", "kind": "person"})
    n = asyncio.run(wh.check(order, [("contactos", "add_contact")], settle_s=0))
    assert n == 1
    assert store == [("contactos", "add_contact", {"name": "Rowan", "kind": "person", "email": "rowan@example.com"})]
    assert [e["status"] for e in _spec.settled()] == ["met"]


def test_another_card_same_class_a_task_gets_the_list_the_order_named(store, monkeypatch):
    order = "Añade dos tareas: comprar papel en la lista casa y llamar a Rowan en la lista trabajo"
    _repair_writes(monkeypatch, _tasks_goal(), "agenda", "add_task", {"title": "Llamar a Rowan"})
    n = asyncio.run(wh.check(order, [("agenda", "add_task")], settle_s=0))
    assert n == 1 and store == [("agenda", "add_task", {"title": "Llamar a Rowan", "list": "trabajo"})]


@pytest.mark.parametrize("order", [
    "Guarda a Quinn y a Rowan; el correo de Rowan es rowan@example.com",
    "Save Quinn and Rowan; Rowan's email is rowan@example.com"])
def test_a_row_that_only_carries_the_name_is_not_the_row_the_order_asked_for(store, monkeypatch, order):
    goal = wh.goal_on(_contacts_goal(), "contactos", order)
    assert goal["all"][1]["with"] == {"email": "rowan@example.com"}
    monkeypatch.setattr(rows, "_rows", lambda w, c: [{"name": "Quinn"}, {"name": "Rowan", "kind": "person"}])
    assert _verify.check(goal) is False
    assert "rowan@example.com" in _verify.missing(goal)[0]
    # the card may file the address anywhere — a list of details, a channel row: the data is what is owed
    monkeypatch.setattr(rows, "_rows", lambda w, c: [
        {"name": "Quinn"}, {"name": "Rowan", "channels": [{"platform": "email", "handle": "Rowan@Example.com"}]}])
    assert _verify.check(goal) is True


def test_a_value_the_model_reshaped_is_not_owed_but_the_row_still_is():
    goal = {"all": [{"widget": "agenda", "collection": "meetings", "where": {"title~": "Dentist"},
                     "with": {"date": "2027-03-12", "location": "Room 4"}}]}
    got = wh.goal_on(goal, "agenda", "Put the dentist on March 12 in Room 4")
    assert got["all"] == [{"widget": "agenda", "collection": "meetings", "where": {"title~": "Dentist"},
                           "with": {"location": "Room 4"}}]


def test_a_field_the_action_does_not_declare_is_never_invented(store):
    goal = {"all": [{"widget": "contactos", "collection": "contacts", "where": {"title~": "Rowan"},
                     "with": {"shoe_size": "44"}}]}
    assert wh.grounded("contactos", "add_contact", {"name": "Rowan"}, goal) == {"name": "Rowan"}
    # what the model already wrote is never overwritten, and a value it filed elsewhere is not added twice
    owed = _contacts_goal()
    assert wh.grounded("contactos", "add_contact", {"name": "Rowan", "email": "r2@example.com"}, owed)["email"] == \
        "r2@example.com"
    put = {"name": "Rowan", "channels": [{"platform": "email", "handle": "rowan@example.com"}]}
    assert wh.grounded("contactos", "add_contact", put, owed) == put


def test_the_inferrer_is_shown_the_fields_each_collection_creates_with():
    assert "email" in _spec.create_fields("contactos", "contacts")
    assert "list" in _spec.create_fields("agenda", "tasks")
    assert _spec.create_fields("agenda", "occurrences") == []
