"""The booking circuit closes: find → book it → move → cancel → put it back (demo passes 108-109, C2-C4, 2026-10-05).

C2 «find me a free 45 minutes tomorrow afternoon… after my last meeting» and C3 «ok book it»: the slot that was
found lived only in the spoken reply, so when the reply went wrong the booking invented 11:45 — beside a 15:00 the
card knew about. The card now KEEPS the slot it found and «book it» with no hour takes it; a booking over another
appointment says so; «the afternoon» is a window, not 08:00; and a cancellation — one appointment, one day of a
series, or the end of a series — goes to a trash that `restore_meeting` brings back as it was.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def ag(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as _d
    for t, s, e in (("Weekly review", "09:00", "09:30"), ("Product meeting", "11:00", "12:00"),
                    ("Architecture", "15:00", "16:00")):
        _d.apply_action("add_meeting", {"title": t, "date": "2026-10-06", "startTime": s, "endTime": e})
    return _d


def _rows(ag, title):
    from widgets import store
    return [m for m in store.load("agenda", {}).get("meetings", []) if m["title"] == title]


def test_the_afternoon_is_a_window(ag):
    got = ag.apply_action("find_free", {"date": "2026-10-06", "duration_min": 45, "from": "afternoon"})
    assert got["window"][0] == "12:00", got
    assert ag.apply_action("find_free", {"date": "2026-10-06", "from": "tarde"})["window"][0] == "12:00"
    assert ag.apply_action("find_free", {"date": "2026-10-06", "from": "00:00"})["window"][0] == "00:00", \
        "midnight is a time, not «no time»"


def test_the_part_of_day_under_another_key_is_the_window(ag):
    """Pass 111, C2: the model sent `{"period": "afternoon", "duration": 45}` and the window was the whole day."""
    got = ag.apply_action("find_free", {"date": "2026-10-06", "period": "afternoon", "duration": 45})
    assert got["window"][0] == "12:00", got


def test_after_last_false_is_false(ag):
    got = ag.apply_action("find_free", {"date": "2026-10-06", "duration_min": 45, "from": "12:00", "after_last": "false"})
    assert got["free"][0]["first_fit"] == "12:00-12:45", got


def test_book_it_takes_the_slot_that_was_found(ag):
    got = ag.apply_action("find_free", {"date": "2026-10-06", "duration_min": 45, "from": "12:00", "after_last": True})
    assert got["free"][0]["first_fit"] == "16:00-16:45", got
    r = ag.apply_action("add_meeting", {"title": "Catch up with Rowan"})
    assert r.get("ok") is not False, r
    row = _rows(ag, "Catch up with Rowan")[0]
    assert (row["date"], row["startTime"], row["endTime"]) == ("2026-10-06", "16:00", "16:45"), row


def test_an_hour_he_says_beats_the_slot_found(ag):
    ag.apply_action("find_free", {"date": "2026-10-06", "duration_min": 45, "from": "12:00", "after_last": True})
    ag.apply_action("add_meeting", {"title": "Call", "date": "2026-10-06", "startTime": "18:00"})
    assert _rows(ag, "Call")[0]["startTime"] == "18:00"


def test_a_stale_slot_is_not_taken(ag, monkeypatch):
    ag.apply_action("find_free", {"date": "2026-10-06", "duration_min": 45, "from": "12:00", "after_last": True})
    db = ag.load_db()
    db["proposed"]["at"] -= 3600
    from widgets import store
    store.save("agenda", db)
    r = ag.apply_action("add_meeting", {"title": "Later thing"})
    assert not _rows(ag, "Later thing") or _rows(ag, "Later thing")[0].get("startTime") != "16:00", r


def test_a_booking_over_another_appointment_says_so(ag):
    r = ag.apply_action("add_meeting", {"title": "Dentist", "date": "2026-10-06", "startTime": "11:30",
                                        "endTime": "12:15"})
    assert [c["title"] for c in r.get("clashes") or []] == ["Product meeting"], r


def test_a_cancelled_appointment_comes_back(ag):
    ag.apply_action("cancel_meeting", {"title": "Architecture", "date": "2026-10-06"})
    assert not _rows(ag, "Architecture")
    r = ag.apply_action("restore_meeting", {})
    assert r.get("ok") is not False, r
    row = _rows(ag, "Architecture")[0]
    assert (row["date"], row["startTime"], row["endTime"]) == ("2026-10-06", "15:00", "16:00")
    assert ag.apply_action("restore_meeting", {}).get("ok") is False, "the trash is empty now"


def test_a_skipped_day_of_a_series_comes_back(ag):
    ag.apply_action("add_meeting", {"title": "Flute", "date": "2026-10-08", "startTime": "18:00", "repeat": "weekly"})
    ag.apply_action("cancel_meeting", {"title": "Flute", "date": "2026-10-15"})
    assert "2026-10-15" in _rows(ag, "Flute")[0]["repeat"].get("skip", [])
    ag.apply_action("restore_meeting", {"title": "flute"})
    assert "2026-10-15" not in (_rows(ag, "Flute")[0]["repeat"].get("skip") or [])


def test_a_series_cut_short_comes_back(ag):
    ag.apply_action("add_meeting", {"title": "Piano", "date": "2026-10-07", "startTime": "17:00", "repeat": "weekly",
                                    "until": "2027-06-30"})
    ag.apply_action("cancel_meeting", {"title": "Piano", "from": "2027-01-01"})
    assert _rows(ag, "Piano")[0]["repeat"]["until"] == "2026-12-31"
    ag.apply_action("restore_meeting", {})
    assert _rows(ag, "Piano")[0]["repeat"]["until"] == "2027-06-30"


def test_the_manifest_declares_the_restore():
    import json
    from pathlib import Path
    import widgets.agenda as pkg
    acts = json.loads((Path(pkg.__file__).parent / "manifest.json").read_text("utf-8"))["actions"]
    assert "restore_meeting" in acts and acts["restore_meeting"].get("confirm") is False


def test_a_stretch_asked_by_its_length_searches_the_stretch(ag):
    """Pass 115, R3: «five days in her vacation where i'm free» came as find_free {date: first day, duration_min:
    7200, note: «… (20 dic 2026 – 4 ene 2027)»} — no `until`, the stretch in words — and ONE day was searched."""
    ag.apply_action("add_meeting", {"title": "Vacation", "date": "2026-12-20", "endDate": "2027-01-04", "allDay": True})
    got = ag.apply_action("find_free", {"date": "2026-12-20", "duration_min": "7200", "note": "cinco días seguidos"})
    assert (got.get("from"), got.get("until")) == ("2026-12-20", "2027-01-04"), got
    got = ag.apply_action("find_free", {"date": "2026-11-02", "duration_min": 4320})
    assert (got.get("from"), got.get("until")) == ("2026-11-02", "2026-11-04"), "three days asked, three searched"
