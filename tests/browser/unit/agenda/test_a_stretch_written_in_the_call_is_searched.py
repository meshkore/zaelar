"""A free-days search whose last day was written in the call's own text searches the whole stretch (demo pass 88).

R3 «find a five-day period during her vacation when my calendar is clear»: the repair pass sent
{date: 2026-12-20, notes: «… vacaciones de Anna (2026-12-20 a 2027-01-04)»} — `notes` is not a key `find_free`
reads — so ONE day was searched and the answer asked him for the dates he had just been told.
"""
import pytest


@pytest.fixture
def ag(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as _d
    return _d


def test_the_last_day_in_the_calls_text_is_the_stretchs_end(ag):
    r = ag.apply_action("find_free", {"date": "2026-12-20", "duration_min": 720,
                                      "notes": "five free days in Anna's vacation (2026-12-20 to 2027-01-04)"})
    assert r["ok"] and r["until"] == "2027-01-04", r
    assert len(r["free_days"]) == 16 and r["booked"] is False


def test_without_a_later_date_it_is_still_one_day(ag):
    one = ag.apply_action("find_free", {"date": "2026-12-20", "duration_min": 45})
    span = ag.apply_action("find_free", {"date": "2026-12-20", "duration_min": 45,
                                         "notes": "anything up to 2026-12-24"})
    assert "until" not in one, "no later date → the one day it was asked about"
    assert span["until"] == "2026-12-24"
