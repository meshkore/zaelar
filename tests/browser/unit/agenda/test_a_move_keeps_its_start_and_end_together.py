"""«Move it 30 minutes later» (demo run, 2026-09-26) came as {newStartTime: 16:45, newEndTime: 17:30}. The END
key was read and the START key was not, so the meeting was STRETCHED to 16:15-17:30 while the reply said «moved
it to 4:45». A move moves both ends."""
import time

import pytest


@pytest.fixture
def ag(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as _d
    return _d


def _tomorrow() -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))


@pytest.mark.parametrize("start_key", ["newStartTime", "new_start_time", "newTime"])
def test_a_move_said_with_start_and_end_moves_both(ag, start_key):
    day = _tomorrow()
    assert ag.apply_action("add_meeting", {"title": "Catch up with Oscar", "date": day,
                                           "startTime": "16:15", "endTime": "17:00"}).get("ok") is not False
    got = ag.apply_action("move_meeting", {"title": "Catch up with Oscar", start_key: "16:45",
                                           "newEndTime": "17:30"})
    assert got.get("ok") is not False, got
    m = got.get("stored") or {}
    assert (m.get("startTime"), m.get("endTime")) == ("16:45", "17:30"), m


@pytest.mark.parametrize("key", ["duration", "durationMinutes", "minutes"])
def test_a_duration_says_the_end_of_a_new_meeting(ag, key):
    """V2-773 final pass (C3): «Schedule it as Catch up with Ethan» arrived as {time: 16:00, duration: 45}; the
    card wrote 16:00–17:00 and told him it could not keep `duration`. The keys `move_meeting` already reads."""
    r = ag.apply_action("add_meeting", {"title": "Catch up with Ethan", "date": "2026-09-27", "time": "16:00", key: 45})
    assert "error" not in r, r
    row = next(m for m in ag.view_data()["meetings"] if m["title"] == "Catch up with Ethan")
    assert (row["startTime"], row["endTime"]) == ("16:00", "16:45"), row
    r2 = ag.apply_action("add_meeting", {"title": "Long one", "date": "2026-09-27", "time": "23:30", key: "90 min"})
    row2 = next(m for m in ag.view_data()["meetings"] if m["title"] == "Long one")
    assert row2["endTime"] == "01:00", row2
