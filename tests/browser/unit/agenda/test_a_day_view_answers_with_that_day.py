"""A day view answers with THAT day's rows (demo pass 31, R2, 2026-09-28).

«when does anna's vacation start? show me in the calendar» → `show_day 2026-12-20`, where «Anna vacation» is.
The turn answered from what the op returned — the card's generic view, i.e. this week — and said «there's nothing
in your calendar about Anna's vacation». `show_day` now returns the day it shows as its `result`, and a data-op's
answer is its `result` when it has one.
"""
import tempfile

import pytest

from nucleo.flash import data_ops


@pytest.fixture
def agenda(monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tempfile.mkdtemp())
    from widgets.agenda import data as A
    A.apply_action("add_meeting", {"title": "Anna vacation", "date": "2026-12-20", "allDay": True})
    A.apply_action("add_meeting", {"title": "Product meeting", "date": "2026-09-29", "time": "11:00"})
    return A


def test_the_day_shown_is_the_answer(agenda):
    res = agenda.apply_action("show_day", {"date": "2026-12-20"})
    ans = data_ops.answer_of(res)
    assert ans == {"result": {"day": "2026-12-20", "meetings": [
        {"title": "Anna vacation", "date": "2026-12-20", "allDay": True, "status": "confirmed"}]}} \
        or [m["title"] for m in ans["result"]["meetings"]] == ["Anna vacation"], ans
    assert "Product meeting" not in str(ans)
