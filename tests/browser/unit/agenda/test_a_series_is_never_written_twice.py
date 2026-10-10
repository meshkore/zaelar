"""A series is never written twice over itself (V2-781 T520, 2026-10-04).

Measured on `weekly-appointment-until-june__us`: «there's no class next Tuesday, take off just that day» → the model
re-wrote the series from the FOLLOWING Tuesday and said «Done»: every Tuesday doubled and the removed class still
there with its notice. The write is refused with what to do instead, so the same turn's corrected retry can skip
the one day (`cancel_meeting {title, date}`), which is what he asked.
"""
from __future__ import annotations

import pytest

from widgets.agenda import data as agenda

SERIES = {"title": "Abril's piano", "date": "2026-10-06", "startTime": "15:15", "endTime": "16:00",
          "repeat": "weekly", "days": "tuesday", "until": "2027-06-30"}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)


def _series():
    return [m for m in agenda.load_db()["meetings"] if isinstance(m.get("repeat"), dict)]


def test_the_same_series_from_its_next_session_is_refused_with_the_op_to_use():
    agenda.apply_action("add_meeting", dict(SERIES))
    r = agenda.apply_action("add_meeting", {**SERIES, "date": "2026-10-13", "days": "martes"})
    assert r.get("ok") is False and r.get("code") == "series_exists", r
    assert "cancel_meeting {title, date: that day}" in r["error"]
    assert len(_series()) == 1


def test_another_weekday_or_another_hour_is_a_new_series():
    agenda.apply_action("add_meeting", dict(SERIES))
    assert agenda.apply_action("add_meeting", {**SERIES, "date": "2026-10-08", "days": "thursday"}).get("ok") is not False
    assert agenda.apply_action("add_meeting", {**SERIES, "date": "2026-10-13", "startTime": "18:00"}).get("ok") is not False
    assert len(_series()) == 3


def test_skipping_the_day_is_what_works():
    agenda.apply_action("add_meeting", dict(SERIES))
    r = agenda.apply_action("cancel_meeting", {"title": "Abril's piano", "date": "2026-10-06"})
    assert r.get("ok") is not False, r
    (s,) = _series()
    assert s["repeat"].get("skip") == ["2026-10-06"], s



def test_the_identical_series_replayed_is_refused_too():
    """V2-781 pair 7 (2026-10-10): with an identical re-add settled as a no-op, «take off just next Tuesday» replayed
    the SAME series, nothing was refused, no corrected retry ran, and the class stayed. Identical is refused too."""
    agenda.apply_action("add_meeting", dict(SERIES))
    r = agenda.apply_action("add_meeting", dict(SERIES))
    assert r.get("ok") is False and r.get("code") == "series_exists", r
    assert len(_series()) == 1
