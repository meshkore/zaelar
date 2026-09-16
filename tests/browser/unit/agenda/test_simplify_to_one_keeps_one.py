"""V2-710 · «Simplify to one» keeps one. It was not a misunderstanding — the action did not exist.

## The session

`7a22136c`, 2026-09-16:

    i=159/175  he      «Okay. I see two. Items today at the same time.»
    i=208      zaelar  «You're right — there are two entries at 11:30 today, both the Tax Agency
                        appointment… They're duplicates of the same appointment. Would you like me to
                        remove one of them?»
    i=217      he      «Yes, please. Simplify to one.»
    i=239      engine  cancel_meeting {"title": "Cita Agencia Tributaria - certificado de persona jurídica"}
    i=263      he      «Okay. I said simplify to one, not delete both.»
    i=374-378  he      «I did tell you to join them to one. The smart move would have been deleting one of
                        those. But you just did delete the two of them.»

## Nothing misread him

`sweep.cancel_meeting` removes every identical copy ON PURPOSE, and its docstring says why: the calendar
once held eleven copies of one «Dentist», those eleven are a sync artifact rather than eleven appointments,
and «which of the eleven?» would be the absurd question. That decision is right and it stays.

The model had no other action to reach for. The gap was in the VOCABULARY: the agenda could cancel an
appointment and it could clear a range, and it had no way to say **leave one**. So this adds the one action
that was missing, and the two share the definition of a duplicate (title + day + hour) so they can never
disagree about what one is.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from widgets import contract, refs, runtime, store
from widgets.agenda import sweep

ENGINE = pathlib.Path(__file__).resolve().parents[4]

#: His calendar at i=159, plus a triple so «keep one» can be told from «keep some».
FIXTURE = {
    "mission": "", "projects": [], "tasks": [], "ideas": [], "recurring": [],
    "user": {"workStart": "09:00", "workEnd": "18:00", "lunchStart": "13:00", "lunchEnd": "14:00",
             "energy": "medium", "wantsExercise": False, "notes": ""},
    "meetings": [
        {"title": "Cita Agencia Tributaria - certificado de persona jurídica", "date": "2026-09-16",
         "startTime": "11:30"},
        {"title": "Cita Agencia Tributaria - certificado de persona jurídica", "date": "2026-09-16",
         "startTime": "11:30"},
        {"title": "Dentist", "date": "2026-09-17", "startTime": "17:00"},
        {"title": "New", "date": "2026-09-18", "startTime": "10:00"},
        {"title": "New", "date": "2026-09-18", "startTime": "10:00"},
        {"title": "New", "date": "2026-09-18", "startTime": "10:00"},
    ],
}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """The store in a throwaway directory AND the Google connector stubbed. `delete_google` talks to his
    REAL calendar and `store.DATA_DIR` does not isolate it — measured the hard way, 29 junk events."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sweep.gcal, "delete_google", lambda m: True)
    from widgets.agenda import data as agenda_data
    monkeypatch.setattr(agenda_data, "_cancel_reminder", lambda m: None)
    store.save("agenda", copy.deepcopy(FIXTURE))
    yield


def _rows(db):
    return sorted((m["title"][:12], m["date"], m.get("startTime", "")) for m in db["meetings"])


# ── 1 · his order ───────────────────────────────────────────────────────────────────────────────────────

def test_simplify_to_one_keeps_one():
    db = copy.deepcopy(FIXTURE)
    res, stuck = sweep.dedupe_meetings(db, {"title": "Agencia Tributaria"})
    assert res["ok"] and res["removed"] == 1 and not stuck
    assert sum(1 for m in db["meetings"] if "Agencia" in m["title"]) == 1, "one survives, and exactly one"
    assert len(db["meetings"]) == 5, "and nothing else was touched"


def test_it_removes_by_IDENTITY_not_by_value():
    """The first version of this used `m not in gone`, and identical copies are EQUAL dicts — so the list
    comprehension dropped the very row the action exists to keep. Caught by running it: three «New» rows
    collapsed to zero instead of one."""
    db = copy.deepcopy(FIXTURE)
    res, _ = sweep.dedupe_meetings(db, {})
    assert res["removed"] == 3 and res["kept"] == 3
    assert _rows(db) == [("Cita Agencia", "2026-09-16", "11:30"),
                         ("Dentist", "2026-09-17", "17:00"),
                         ("New", "2026-09-18", "10:00")]


def test_a_day_can_be_narrowed():
    db = copy.deepcopy(FIXTURE)
    res, _ = sweep.dedupe_meetings(db, {"date": "2026-09-18"})
    assert res["removed"] == 2
    assert sum(1 for m in db["meetings"] if "Agencia" in m["title"]) == 2, "the other day is untouched"


def test_nothing_to_collapse_touches_nothing_and_SAYS_so():
    db = copy.deepcopy(FIXTURE)
    res, _ = sweep.dedupe_meetings(db, {"title": "Dentist"})
    assert res["ok"] and res["removed"] == 0 and "no duplicates" in res["detail"]
    assert len(db["meetings"]) == 6


def test_a_title_that_matches_nothing_asks_instead_of_sweeping():
    db = copy.deepcopy(FIXTURE)
    res, _ = sweep.dedupe_meetings(db, {"title": "zzz nothing like this"})
    assert not res["ok"] and res["error"] == "not_found"
    assert len(db["meetings"]) == 6, "an unmatched selector NEVER means «all of them» (V2-705)"


# ── 2 · the decision that stays ─────────────────────────────────────────────────────────────────────────

def test_cancel_meeting_still_takes_every_copy():
    """Its own docstring is the reason: eleven identical copies of one «Dentist» are one appointment, and
    «which of the eleven?» is the absurd question. Two actions, two meanings, one definition of duplicate."""
    db = copy.deepcopy(FIXTURE)
    res, _ = sweep.cancel_meeting(db, {"title": "Agencia Tributaria"})
    assert res["ok"] and res["removed"] == 2
    assert not any("Agencia" in m["title"] for m in db["meetings"])


def test_both_functions_group_duplicates_THROUGH_THE_SAME_FUNCTION():
    """`cancel_meeting` calls a group ONE appointment (so it takes every copy instead of asking «which of
    the eleven?») and `dedupe_meetings` keeps one member of it. Two callers, opposite conclusions, and they
    must never disagree about what a group IS — so there is one `dup_key`, not two copies of the tuple.
    Two earlier versions of this test counted the SOURCE TEXT and both failed — the first because the two
    spellings had already drifted apart on a line break, the second because that tuple has legitimate other
    uses in this module. Counting characters was never the property; agreeing on a grouping is. So this
    asserts it through BEHAVIOUR: the same group, read by the function both callers use, plus the two
    callers reaching opposite conclusions from it on the same rows."""
    a = {"title": "Dentist", "date": "2026-09-17", "startTime": "17:00"}
    b = {"title": " dentist ", "date": "2026-09-17", "startTime": "17:00", "notes": "different notes"}
    assert sweep.dup_key(a) == sweep.dup_key(b), "same title/day/hour is one appointment"
    assert sweep.dup_key(a) != sweep.dup_key(dict(a, startTime="18:00"))
    # …and the two callers, on rows they must group identically: one keeps a member, the other takes all.
    pair = [dict(a), dict(a)]
    d1, d2 = {"meetings": [dict(m) for m in pair]}, {"meetings": [dict(m) for m in pair]}
    kept, _ = sweep.dedupe_meetings(d1, {"title": "Dentist"})
    took, _ = sweep.cancel_meeting(d2, {"title": "Dentist"})
    assert kept["removed"] == 1 and len(d1["meetings"]) == 1
    assert took["removed"] == 2 and d2["meetings"] == []


# ── 3 · declared, reachable and gated ───────────────────────────────────────────────────────────────────

def test_the_action_is_DECLARED_with_its_gate():
    acts = json.loads((ENGINE / "widgets/agenda/manifest.json").read_text())["actions"]
    spec = acts["dedupe_meetings"]
    assert spec.get("confirm") is True and spec.get("confirm_q"), "it removes rows — it asks first"
    assert spec.get("ref") == "title"
    assert "dedupe_meetings" in acts["cancel_meeting"]["desc"], \
        "cancel_meeting has to point at it, or the model keeps reaching for the only verb it knows"


def test_the_selector_is_optional_and_both_readers_agree():
    """«quita los duplicados» names no appointment on purpose. `contract` must not refuse it for a missing
    selector, and `refs` must not either — the V2-708 disagreement, one action later."""
    assert refs.id_field_for_action("agenda", "dedupe_meetings") == "title"
    assert refs.selector_is_optional("agenda", "dedupe_meetings") is True
    assert contract.selector_for("agenda", "dedupe_meetings") == ""
    assert contract.guard("agenda", "dedupe_meetings", {}) is None, "an empty payload is a legal whole-sweep"


def test_it_reaches_its_handler_through_the_funnel():
    from widgets.agenda import data as agenda_data
    out = agenda_data.apply_action("dedupe_meetings", {"title": "Agencia Tributaria"})
    assert out.get("ok") is True and out["result"]["removed"] == 1
    assert sum(1 for m in store.load("agenda")["meetings"] if "Agencia" in m["title"]) == 1, \
        "…and it PERSISTED — the handler that forgets to save reports success over unchanged data"


def test_it_is_classified_as_a_confirm_action():
    from widgets import actions as wactions
    spec = ((runtime.get("agenda") or {}).get("actions") or {})["dedupe_meetings"]
    assert wactions.classify(spec, "dedupe_meetings") == wactions.CONFIRM
    assert contract.is_destructive(spec, "dedupe_meetings") is True
