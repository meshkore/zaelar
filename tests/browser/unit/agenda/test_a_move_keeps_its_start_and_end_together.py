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
