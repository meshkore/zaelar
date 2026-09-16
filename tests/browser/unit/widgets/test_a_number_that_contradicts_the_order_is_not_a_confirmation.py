"""V2-707 F6 · The confirm gate COMPARES the radius with the count the order named.

## The session

`080b96a7`, 2026-09-16. He had just told it, in English, that Thursday the 17th had three all-day items,
and asked:

    i=10730  he       «Can you clean the three?»
    i=10753  engine   widget/data:clear_range {from: 2026-09-17, to: 2026-09-17}  (mode=confirm)
    i=10756  gate     «Voy a borrar 5 citas del 2026-09-17. Es permanente. ¿Las borro?»
    i=10771  he       «Yes.»
    i=10780  engine   clear_range executed — five rows gone

The number in that question is not an accident: V2-693 put it there precisely so «a confirmation that does
not count what it takes away» could not be said yes to blindly. What the gate never did is COMPARE. Three
and five are not a question and its answer; they are two claims about the same act, and a «yes» to a
contradiction authorises nothing.

Thirty seconds earlier he had also said «Do not speak Spanish» (i=10599). That half of the same defect is
measured in `tests/infrastructure/unit/core/test_what_the_operator_hears_is_in_his_language.py`.

## What is pinned here

The COMPARISON, in both directions — a number that disagrees refuses and registers nothing; a number that
agrees, or no number at all, leaves the confirmation exactly as it was. And the reader that makes it safe:
`asked_count.named` must not read a DATE as a count, or this door would start refusing correct orders,
which is the same failure pointed the other way.
"""
from __future__ import annotations

import pytest

from nucleo import asked_count
from voice.engine.llm.providers import confirm_gate as gate

DAY = "2026-09-17"
_ORDER = "Can you clean the three?"


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    """ISOLATED store — this must never reach the operator's real calendar."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.agenda import data as ag
    db = ag.load_db()
    db["meetings"] = [
        {"id": "a1", "title": "Task one", "date": DAY, "allDay": True},
        {"id": "a2", "title": "Task two", "date": DAY, "allDay": True},
        {"id": "a3", "title": "Task three", "date": DAY, "allDay": True},
        {"id": "a4", "title": "Dentist", "date": DAY, "startTime": "17:00"},
        {"id": "a5", "title": "Standup", "date": DAY, "startTime": "09:00"},
    ]
    store.save(ag.WIDGET_ID, db)
    return ag


def _decide(order, payload=None):
    return gate.decide("agenda", "clear_range", payload or {"from": DAY, "to": DAY}, order)


# ── 1 · the count the ORDER named ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Can you clean the three?", 3),                 # THE measured order
    ("I need you to cancel and delete all four. Right now.", 4),   # i=10403, and there it MATCHED
    ("borra las tres", 3),
    ("quita esas dos", 2),
    ("clean both of them", 2),
    ("delete 3 appointments", 3),                    # a digit needs its counted noun
    ("borra 5 citas", 5),
])
def test_a_count_in_the_order_is_read(text, expected):
    assert asked_count.named(text) == expected


@pytest.mark.parametrize("text", [
    "clean the 17th",                    # A DATE. Reading this as a count would refuse a correct order.
    "Now on Thursdays, the seventeenth,",  # i=10644 — an ordinal is a different word and never matches
    "delete the third one",
    "borra la tercera",
    "at three",                          # a time
    "September three",
    "I set clean today.",                # i=10490 — a radius with no count on it
    "limpia la agenda entera",
    "delete all of them",                # «all» names a radius, not a number
])
def test_what_is_NOT_a_count_is_left_alone(text):
    assert asked_count.named(text) is None


# ── 2 · the comparison ──────────────────────────────────────────────────────────────────────────────────

def test_the_measured_order_is_REFUSED_instead_of_confirmed(agenda):
    d = _decide(_ORDER)
    assert d["kind"] == "mismatch", d
    assert (d["asked"], d["n"]) == (3, 5)
    assert "3" in d["sentence"] and "5" in d["sentence"], "both numbers, or he cannot see the disagreement"
    for title in ("Task one", "Dentist", "Standup"):
        assert title in d["sentence"], "the rows are NAMED so he can say which ones he meant"


def test_and_NOTHING_is_registered_so_a_later_yes_executes_nothing(agenda):
    """The whole point. On 2026-09-16 the confirmation was registered with that question and his «Yes.»
    found a mutation waiting for it."""
    from widgets import confirm as wconfirm
    wconfirm.reset()
    d = _decide(_ORDER)
    assert d["kind"] == "mismatch"
    assert not wconfirm.pending(), "a contradiction must leave nothing for a «yes» to resolve"


def test_a_count_that_AGREES_confirms_exactly_as_before(agenda):
    d = _decide("delete all five")
    assert d["kind"] == "ask"
    assert "5" in d["question"] and d["op"]["action"] == "clear_range"


def test_an_order_with_NO_count_confirms_exactly_as_before(agenda):
    """Most orders name a radius without counting it, and this door must not touch them."""
    d = _decide("clean tomorrow")
    assert d["kind"] == "ask" and "5" in d["question"]


def test_an_EMPTY_radius_does_not_open_a_confirmation_either(agenda):
    """i=10578→10609: a range with nothing in it was registered as a confirmation whose «question» was the
    statement «No hay ninguna cita que borrar en ese tramo.» — a yes/no with no question in it."""
    from widgets import confirm as wconfirm
    wconfirm.reset()
    d = _decide("clean that week", {"from": "2027-01-01", "to": "2027-01-02"})
    assert d["kind"] == "empty"
    assert not wconfirm.pending()


def test_a_keeper_is_counted_the_way_the_DELETION_counts_it(agenda):
    """The radius reads `sweep.window`/`sweep.kept` — the same module the action uses. A question that
    counts differently from the deletion it gates is worse than no question."""
    r = gate.radius("agenda", "clear_range", {"from": DAY, "to": DAY, "keep": "Dentist"})
    assert r["n"] == 4 and [m["title"] for m in r["kept"]] == ["Dentist"]
    assert _decide("clean the four", {"from": DAY, "to": DAY, "keep": "Dentist"})["kind"] == "ask"


# ── 3 · the door speaks both shipped languages ──────────────────────────────────────────────────────────

def test_the_refusal_is_in_the_operators_language(agenda):
    from tests.lang import speaking
    with speaking("en"):
        en = _decide(_ORDER)["sentence"]
    with speaking("es"):
        es = _decide("¿puedes limpiar las tres?")["sentence"]
    assert en != es
    assert "asked me for" in en and "pedido" in es
    assert "pedido" not in en, "the sentence he heard in Castilian mid-English-session is the other half"


# ── 4 · the RADIUS reader answers None where it cannot count, and the gate then behaves as before ────────

def test_an_action_with_no_countable_radius_is_untouched(agenda):
    """`cancel_meeting` names ONE row: there is nothing to compare, and a count in the sentence would be
    the door inventing a disagreement."""
    assert gate.radius("agenda", "cancel_meeting", {"title": "Dentist"}) is None
    d = gate.decide("agenda", "cancel_meeting", {"title": "Dentist"}, "delete the three")
    assert d["kind"] == "ask"


def test_the_generic_data_door_shares_the_same_radius(agenda):
    """V2-707 F1's `rows.plan` already counts; this reads IT rather than re-deriving, so the two cannot
    disagree about the same calendar — the defect F0 had just fixed one layer down."""
    r = gate.radius("agenda", "rows.delete", {"collection": "meetings", "where": {"allDay": True}})
    assert r["n"] == 3 and sorted(r["names"]) == ["Task one", "Task three", "Task two"]
    assert gate.decide("agenda", "rows.delete",
                       {"collection": "meetings", "where": {"allDay": True}},
                       "clean the three")["kind"] == "ask"
    assert gate.decide("agenda", "rows.delete",
                       {"collection": "meetings", "where": {"date": DAY}},
                       "clean the three")["kind"] == "mismatch"
