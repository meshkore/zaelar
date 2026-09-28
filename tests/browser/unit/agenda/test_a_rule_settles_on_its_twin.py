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


def test_finding_free_time_is_an_action_that_books_nothing(ag, monkeypatch):
    """Demo passes 2026-09-28 (C2, three running): «find me a free 45 minutes tomorrow afternoon to talk with ethan»
    booked the meeting — the description said it was a question, but the agenda had no action that FINDS time, so
    the model took the nearest one, which writes. `find_free` answers the question and writes no meeting."""
    ag.apply_action("add_meeting", {"title": "Weekly review", "date": "2026-10-06", "startTime": "09:00",
                                    "endTime": "09:30"})
    ag.apply_action("add_meeting", {"title": "Architecture", "date": "2026-10-06", "startTime": "15:00",
                                    "endTime": "15:30"})
    before = len(ag.load_db()["meetings"])
    got = ag.apply_action("find_free", {"date": "2026-10-06", "duration_min": 45, "from": "12:00",
                                        "after_last": True})
    assert got["ok"] and got["booked"] is False
    assert got["free"][0]["first_fit"] == "15:30-16:15", got
    assert len(ag.load_db()["meetings"]) == before, "a question wrote a meeting"
    assert ag.load_db()["view"]["sel"] == "2026-10-06", "the card shows the day he asked about"
    from widgets import effects as fx
    assert fx.carries("agenda", "find_free", fx.DATA_READ) and not fx.carries("agenda", "find_free", fx.DATA_WRITE)



def test_free_days_across_a_stretch_are_found_without_booking(ag):
    """full18 R3: «find me five days in her vacation where i'm free» — find_free looked at one day only, the model
    called nothing and the turn went to a worker. With `until` it reads every day of the stretch; her vacation
    (all-day) blocks nothing by the clock."""
    ag.apply_action("add_meeting", {"title": "Anna vacation", "date": "2026-12-20", "until": "2027-01-04",
                                    "allDay": True})
    ag.apply_action("add_meeting", {"title": "Dentist", "date": "2026-12-22", "startTime": "10:00",
                                    "endTime": "11:00"})
    before = len(ag.load_db()["meetings"])
    got = ag.apply_action("find_free", {"date": "2026-12-20", "until": "2026-12-24"})
    assert got["ok"] and got["booked"] is False
    assert got["free_days"] == ["2026-12-20", "2026-12-21", "2026-12-23", "2026-12-24"], got
    assert [d["date"] for d in got["days_with_appointments"]] == ["2026-12-22"]
    assert len(ag.load_db()["meetings"]) == before
