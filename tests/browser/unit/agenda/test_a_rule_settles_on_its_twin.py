"""A second write of the SAME appointment that carries the rule the row lacks settles it on the row (V2-773).

«Anna vacation, December 20 through January 4» reached the card twice from the demo's INIT list (2026-09-27):
first as one all-day entry, then — the repair pass, with the end date — as a daily span. The twin rule saw the
same title on the same day and dropped the richer write: her vacation was a single day on the calendar."""
import pytest


@pytest.fixture
def ag(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as _d
    return _d


def _rows(ag, title):
    """The STORED rows — `view_data` unrolls a series into its occurrences, which is the point: one row, many days."""
    from widgets import store
    return [m for m in store.load("agenda", {}).get("meetings", []) if m["title"] == title]


def test_the_all_day_twin_becomes_the_span(ag):
    assert ag.apply_action("add_meeting", {"title": "Anna vacation", "date": "2026-12-20", "startTime": "00:00",
                                           "endTime": "23:59", "allDay": True}).get("ok") is not False
    r = ag.apply_action("add_meeting", {"title": "Anna vacation", "date": "2026-12-20", "endDate": "2027-01-04",
                                        "allDay": True})
    assert r.get("ok") is not False, r
    rows = _rows(ag, "Anna vacation")
    assert len(rows) == 1, "still ONE row — the twin rule holds"
    rep = rows[0].get("repeat") or {}
    assert (rep.get("freq"), rep.get("until")) == ("daily", "2027-01-04"), (
        f"THE BUG: the span was dropped as a duplicate — {rows[0]}")
    assert (r.get("stored") or {}).get("repeat") == rep, "the reply describes the row as it now is"
    days = {m["date"] for m in ag.view_data()["meetings"] if m["title"] == "Anna vacation"}
    assert {"2026-12-20", "2026-12-25", "2027-01-04"} <= days and "2027-01-05" not in days, sorted(days)


def test_the_timed_twin_takes_a_series(ag):
    ag.apply_action("add_meeting", {"title": "Yoga", "date": "2026-10-01", "startTime": "18:00", "endTime": "19:00"})
    r = ag.apply_action("add_meeting", {"title": "Yoga", "date": "2026-10-01", "startTime": "18:00", "endTime": "19:00",
                                        "repeat": "weekly", "until": "2026-12-31"})
    assert r.get("ok") is not False, r
    rows = _rows(ag, "Yoga")
    assert len(rows) == 1 and (rows[0].get("repeat") or {}).get("freq") == "weekly", rows


def test_a_rule_the_row_already_has_is_not_overwritten_by_a_twin(ag):
    ag.apply_action("add_meeting", {"title": "Yoga", "date": "2026-10-01", "startTime": "18:00", "endTime": "19:00",
                                    "repeat": "weekly", "until": "2026-12-31"})
    ag.apply_action("add_meeting", {"title": "Yoga", "date": "2026-10-01", "startTime": "18:00", "endTime": "19:00",
                                    "repeat": "daily", "until": "2026-10-10"})
    rows = _rows(ag, "Yoga")
    assert len(rows) == 1 and rows[0]["repeat"]["freq"] == "weekly", "changing a rule is update_meeting's, with his words"


def test_a_stay_of_several_days_is_declared_so_the_model_can_ask_for_it(ag):
    """Demo pass 2026-09-28 (full13 INIT): «December 20, 2026 through January 4, 2027: Anna vacation» — the model
    answered «I can't make a single event span two weeks» and wrote nothing. The card has taken a span since V2-771
    (`until` with no rule); the manifest only described `until` as the end of a REPETITION, so a stay was a thing
    the model had no name for. The declared shape — `allDay` + `date` + `until`, no `repeat` — is one row, every day."""
    import json
    from pathlib import Path
    add = json.loads((Path(ag.__file__).parent / "manifest.json").read_text("utf-8"))["actions"]["add_meeting"]
    assert "VARIOS DÍAS" in add["desc"] and "tramo" in add["payload"]["until"], "the span is not declared"
    r = ag.apply_action("add_meeting", {"title": "Anna vacation", "date": "2026-12-20", "until": "2027-01-04",
                                        "allDay": True})
    assert r.get("ok") is not False, r
    assert len(_rows(ag, "Anna vacation")) == 1
    days = {m["date"] for m in ag.view_data()["meetings"] if m["title"] == "Anna vacation"}
    assert {"2026-12-20", "2027-01-01", "2027-01-04"} <= days and "2027-01-05" not in days, sorted(days)


def test_finding_a_free_slot_is_declared_a_question_not_a_booking(ag):
    """Demo passes 2026-09-28 (full12, full13 C2): «find me a free 45 minutes tomorrow afternoon to talk with ethan»
    booked «Call with Ethan» on his real calendar; the next order («ok book it, call it catch up with ethan») then
    booked a SECOND one at the same hour and C4 had to ask which to move. The only description of `add_meeting`
    the model reads said what it adds, never when it must not."""
    import json
    from pathlib import Path
    desc = json.loads((Path(ag.__file__).parent / "manifest.json").read_text("utf-8"))["actions"]["add_meeting"]["desc"]
    assert "SOLO cuando él pide" in desc and "es una PREGUNTA" in desc


def test_booking_the_slot_just_booked_renames_it_instead_of_doubling_it(ag):
    """Demo passes 2026-09-28 (full12-full15, C2→C3): the ambiguous «find me a free 45 minutes… to talk with ethan»
    got booked as «Call with Ethan»; «ok book it, call it catch up with ethan» then booked a SECOND one in the same
    slot and «move it half an hour later» had to ask which."""
    slot = {"date": "2026-10-06", "startTime": "16:00", "endTime": "16:45"}
    ag.apply_action("add_meeting", {"title": "Call with Ethan", **slot})
    r = ag.apply_action("add_meeting", {"title": "Catch up with Ethan", **slot})
    assert r.get("renamed") and [m["title"] for m in _rows(ag, "Catch up with Ethan")] == ["Catch up with Ethan"]
    assert not _rows(ag, "Call with Ethan"), "one appointment, under the name he gave it last"
    ag.apply_action("add_meeting", {"title": "Lunch with Laura", "date": "2026-10-06", "startTime": "16:30",
                                    "endTime": "17:30"})
    assert _rows(ag, "Lunch with Laura") and _rows(ag, "Catch up with Ethan"), "another slot is another meeting"
    import time as _t
    from widgets import store
    db = store.load("agenda", {})
    db["focus"]["at"] = _t.time() - 3600                          # the conversation moved on
    store.save("agenda", db)
    ag.apply_action("add_meeting", {"title": "Dentist", **slot})
    assert _rows(ag, "Dentist") and _rows(ag, "Catch up with Ethan"), "a stale focus renames nothing"
