"""V2-720 — «delete all of today except Ivan's meeting» never becomes «delete all of today».

## The measured incident

Session `e22cdba8`, 2026-09-17 22:01. The operator, looking at his agenda, said it three times:

    «Can you delete all the items but the meeting with Ivan?»
    «Please do not delete the meeting with Ivan.»
    «Delete the others and ask me for confirmation.»

What ran, with no question asked, was:

    agenda:clear_range {"from": "hoy", "to": "hoy", "keep": {"title": "Approval rules: who signs off"}}

The exception was there, correctly shaped — and aimed at an appointment that was not in the day. `kept()`
answered False for every row, the keeper evaporated, and the whole day went with Ivan's ten o'clock inside
it. Then the model told him his agenda «didn't let me specify an exception», escalated a Brain Worker task
to build the capability that already existed, and that task's first step DELETED the agenda widget.

Three seams failed, one per test class below, and none of them is about words:

  1. **A keeper that names nothing became a full deletion.** `rows.plan` has said since V2-707 that on a
     destructive op «nothing matched» is a misunderstanding and never a silent no-op; the sweep, one floor
     down, let it mean «everything».
  2. **A day of deletions was charged one appointment's friction.** The manifest says `confirm: true`;
     `_scope` read the action's selector — `from`, a DATE — found it filled and answered «names one thing»,
     so the consent rule's radius rail (V2-707: more than one asks) never saw a radius above 1. The gate is
     the RADIUS, not the verb, and nobody was counting rows.
  3. **«All of these except those» could not be said.** The generic door's `where` only takes; the exception
     had to be smuggled in as a not-equal, which reads correctly for ONE name and inverts for a list.
"""
from __future__ import annotations

import asyncio

import pytest

from widgets import rows, store

TODAY = "2026-09-17"
DAY = [
    {"id": "m1", "title": "Meeting with Ivan Mikushin", "date": TODAY, "startTime": "10:00"},
    {"id": "m2", "title": "Dentist test", "date": TODAY, "startTime": "11:00"},
    {"id": "m3", "title": "Agency visit", "date": TODAY, "startTime": "12:00"},
    {"id": "m4", "title": "Call with the bank", "date": TODAY, "startTime": "13:00"},
]
TOMORROW = {"id": "m5", "title": "Tomorrow thing", "date": "2026-09-18", "startTime": "09:00"}

#: The call as it really arrived — a well-formed keeper naming something that is not there.
PHANTOM = {"from": TODAY, "to": TODAY, "keep": {"title": "Approval rules: who signs off"}}
#: The same call aimed at a title that IS there, spoken the way he spoke it.
REAL = {"from": TODAY, "to": TODAY, "keep": {"title": "the meeting with Ivan"}}


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.agenda import data as ag
    db = ag.load_db()
    db["meetings"] = [dict(m) for m in DAY] + [dict(TOMORROW)]
    store.save(ag.WIDGET_ID, db)
    return ag


def titles(ag) -> list[str]:
    return [m.get("title") for m in ag.load_db().get("meetings", [])]


# ── 1 · a keeper that names nothing is a refusal, never a deletion ───────────────────────────────────────

def test_the_call_that_deleted_ivans_meeting_now_deletes_nothing(agenda):
    from widgets.agenda import sweep
    db = agenda.load_db()
    res, stuck = sweep.clear_range(db, PHANTOM)
    assert res["ok"] is False and res["error"] == "keep_not_found"
    assert res["removed"] == 0 and stuck == []
    assert [m["title"] for m in db["meetings"]] == [m["title"] for m in DAY] + [TOMORROW["title"]]


def test_the_refusal_names_the_keeper_that_was_not_there_and_what_is(agenda):
    """A refusal the model cannot act on is a dead end (the `deny_reason` lesson): it has to carry the list
    the keeper should have been picked from, so the retry aims at a real title."""
    from widgets.agenda import sweep
    res, _ = sweep.clear_range(agenda.load_db(), PHANTOM)
    assert res["missing"] == ["Approval rules: who signs off"]
    assert "Meeting with Ivan Mikushin" in res["options"] and "Agency visit" in res["options"]
    assert "Approval rules" in res["detail"]


def test_nothing_is_persisted_when_the_keeper_is_a_phantom(agenda):
    """Through the widget's own door, which is what the voice channel calls: the store must be untouched."""
    out = agenda.apply_action("clear_range", dict(PHANTOM))
    assert out["ok"] is False
    assert titles(agenda) == [m["title"] for m in DAY] + [TOMORROW["title"]]


def test_a_keeper_that_is_really_there_still_sweeps_the_rest(agenda):
    """The capability itself is untouched — V2-693 keeps working, and his own words still find the row."""
    out = agenda.apply_action("clear_range", dict(REAL))
    assert out["ok"] is True and out["result"]["removed"] == 3
    assert titles(agenda) == ["Meeting with Ivan Mikushin", "Tomorrow thing"]


def test_one_real_keeper_and_one_phantom_still_refuses(agenda):
    """Partial credit is the dangerous reading: if one of the two names does not exist, the sweep is built
    on a wrong belief about the day and the rows it would delete are not the ones he meant."""
    from widgets.agenda import sweep
    res, _ = sweep.clear_range(agenda.load_db(),
                               {**PHANTOM, "keep": ["the meeting with Ivan", "Approval rules: who signs off"]})
    assert res["ok"] is False and res["missing"] == ["Approval rules: who signs off"]
    assert titles(agenda) == [m["title"] for m in DAY] + [TOMORROW["title"]]


def test_a_sweep_with_no_exception_at_all_is_not_touched(agenda):
    out = agenda.apply_action("clear_range", {"from": TODAY, "to": TODAY})
    assert out["ok"] is True and out["result"]["removed"] == 4
    assert titles(agenda) == ["Tomorrow thing"]


# ── 2 · the radius of a sweep is its rows, and more than one asks ────────────────────────────────────────

def test_the_widget_counts_what_the_call_would_delete(agenda):
    assert agenda.radius("clear_range", REAL) == 3        # the day minus Ivan's
    assert agenda.radius("clear_range", PHANTOM) == 4     # the phantom keeps nothing: the whole day
    assert agenda.radius("clear_range", {"from": "2026-09-20", "to": "2026-09-20"}) == 0
    assert agenda.radius("add_meeting", {"title": "x"}) is None   # not a sweep: not counted


def test_the_day_sweep_asks_because_it_touches_more_than_one(agenda):
    """The turn he actually spoke: `confirm: true` in the manifest and `fast` in the call, while he was
    saying «and ask me for confirmation»."""
    from nucleo.flash import frontend
    from widgets import actions as _wa
    assert frontend.action_mode("agenda", "clear_range") == _wa.CONFIRM
    assert frontend.action_mode_now("agenda", "clear_range", PHANTOM) == _wa.CONFIRM
    assert frontend.action_mode_now("agenda", "clear_range", REAL) == _wa.CONFIRM


def test_the_verdict_carries_the_real_count_so_the_question_can_name_it(agenda):
    from nucleo.flash import frontend
    v = frontend.action_verdict("agenda", "clear_range", REAL)
    assert v["n"] == 3 and v["verdict"] != "run"


def test_a_sweep_that_would_delete_exactly_one_keeps_its_old_answer(agenda):
    """The rail is «more than one», not «any sweep»: a window holding a single appointment is the same act
    as cancelling that appointment, and this must not grow friction that V2-712 removed."""
    from nucleo.flash import frontend
    one = {"from": "2026-09-18", "to": "2026-09-18"}
    assert agenda.radius("clear_range", one) == 1
    assert frontend.action_mode_now("agenda", "clear_range", one) == "fast"


def test_a_widget_without_the_hook_decides_exactly_as_before(agenda):
    """The hook REFINES (the `consent_scope` shape): an unreadable or absent count keeps the old verdict."""
    from nucleo.flash import frontend
    assert frontend._declared_radius("mensajeria", "send_to", {"to": "Ivan"}) is None
    assert frontend._declared_radius("nope", "whatever", {}) is None


def test_the_worker_gate_gets_the_same_answer(agenda):
    """One consent rule, two mouths (V2-719): the Brain Worker cannot run the sweep the voice must ask for."""
    from nucleo.worker_policy import CONFIRM, classify_act
    assert classify_act("widget_data", {"widget_id": "agenda", "action": "clear_range",
                                        "payload": dict(PHANTOM)}) == CONFIRM


# ── 3 · groups: «all of these except those», and the exact rows by id ────────────────────────────────────

def test_the_sentence_he_said_is_now_one_expression(agenda):
    g = rows.group("agenda", "meetings", {"collection": "meetings", "where": {"date": TODAY},
                                          "not": {"title~": "ivan"}})
    assert [r["title"] for r in g] == ["Dentist test", "Agency visit", "Call with the bank"]


def test_several_exceptions_are_several_clauses(agenda):
    g = rows.group("agenda", "meetings", {"collection": "meetings", "where": {"date": TODAY},
                                          "not": [{"title~": "ivan"}, {"title~": "dentist"}]})
    assert [r["title"] for r in g] == ["Agency visit", "Call with the bank"]


def test_a_negated_list_means_none_of_them_and_not_any_of_them(agenda):
    """The inversion that made the old way unusable: «every row differs from at least one of these» is true
    of every row, so a three-name exception selected the whole collection, the three keepers included."""
    g = rows.group("agenda", "meetings", {"collection": "meetings",
                                          "where": {"date": TODAY,
                                                    "title!": ["Meeting with Ivan Mikushin", "Dentist test"]}})
    assert [r["title"] for r in g] == ["Agency visit", "Call with the bank"]


def test_a_group_can_be_listed_first_and_then_acted_on_by_id(agenda):
    """«Prepare a group of items and work with them»: list what is really there, pick from THAT, act on
    exactly those — which is the route that would have kept Ivan's meeting without any exception at all."""
    listed = asyncio.run(rows.apply("agenda", "list", {"collection": "meetings", "where": {"date": TODAY}}))
    assert listed["n"] == 4
    keep = "Meeting with Ivan Mikushin"
    ids = [r["title"] for r in listed["rows"] if r["title"] != keep]   # `meetings` declares id = title
    g = rows.group("agenda", "meetings", {"collection": "meetings", "ids": ids})
    assert [r["title"] for r in g] == ["Dentist test", "Agency visit", "Call with the bank"]


def test_an_exception_wins_over_an_id_that_contradicts_it(agenda):
    """A contradiction on a destructive call is read the way that touches less."""
    g = rows.group("agenda", "meetings", {"collection": "meetings", "ids": ["Dentist test", "Agency visit"],
                                          "not": {"title~": "dentist"}})
    assert [r["title"] for r in g] == ["Agency visit"]


def test_the_group_delete_asks_with_the_names_and_then_runs_one_by_one(agenda):
    """The whole shape the operator described: the radius gate asks with the count and the names, and each
    row then goes through the widget's OWN `cancel_meeting` — so the Google mirror, the canvas refresh and
    the V2-705 contract all still happen, and the kept row is never in the group."""
    call = {"collection": "meetings", "where": {"date": TODAY}, "not": {"title~": "ivan"}}
    p = rows.plan("agenda", "delete", call)
    assert p["n"] == 3 and p["confirm"] is True and p["via"] == "cancel_meeting"
    assert "Meeting with Ivan Mikushin" not in p["names"]

    asked = asyncio.run(rows.apply("agenda", "delete", call))
    assert asked["needs_confirm"] is True and asked["n"] == 3
    assert titles(agenda) == [m["title"] for m in DAY] + [TOMORROW["title"]]   # asking changed nothing

    done = asyncio.run(rows.apply("agenda", "delete", call, confirmed=True))
    assert done["ok"] is True and done["done"] == 3
    assert titles(agenda) == ["Meeting with Ivan Mikushin", "Tomorrow thing"]


def test_a_group_that_matches_nothing_is_still_refused(agenda):
    out = asyncio.run(rows.apply("agenda", "delete", {"collection": "meetings", "where": {"date": TODAY},
                                                      "not": {"date": TODAY}}))
    assert out["ok"] is False and out["error"] == rows.NOTHING_MATCHED
    assert titles(agenda) == [m["title"] for m in DAY] + [TOMORROW["title"]]


def test_a_collection_with_no_declared_action_uses_the_planned_rows(agenda, tmp_path, monkeypatch):
    """The fallback writer (a generated widget with a plain list) must delete the rows the CONFIRM question
    described, not re-read `where` and quietly widen back to the group without its exceptions."""
    monkeypatch.setattr(rows, "declared", lambda wid: {"meetings": {"id": "title", "label": "title"}})
    call = {"collection": "meetings", "where": {"date": TODAY}, "not": {"title~": "ivan"}}
    done = asyncio.run(rows.apply("agenda", "delete", call, confirmed=True))
    assert done["done"] == 3
    assert titles(agenda) == ["Meeting with Ivan Mikushin", "Tomorrow thing"]
