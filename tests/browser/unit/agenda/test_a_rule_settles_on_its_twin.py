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
