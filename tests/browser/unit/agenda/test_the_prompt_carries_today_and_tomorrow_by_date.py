"""The prompt's agenda block carries TODAY and TOMORROW, each under its own date (demo pass 110, Z1, 2026-10-05).

«what's on my plate tomorrow» was answered with TODAY's four meetings — the only day the block carried, under a
header that said «today» once, at the top — and then «Hold on, I need to correct that…» after the model's own
read of the card. Tomorrow is the other day everybody asks about (C1 and Z1 of the demo both do), so it rides in
the same block, and each day is named by its date: the model is not left to work out which day a row belongs to.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def ag(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real agenda."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as d
    monkeypatch.setattr(d, "_today", lambda: "2026-10-05")
    return d


def _add(ag, title, date, start):
    ag.apply_action("add_meeting", {"title": title, "date": date, "startTime": start})


def test_both_days_ride_each_under_its_date(ag):
    _add(ag, "Intro chat", "2026-10-05", "16:15")
    _add(ag, "Call with accountant", "2026-10-06", "10:00")
    block = ag.today_line()
    assert "2026-10-05" in block and "2026-10-06" in block, block
    today, tomorrow = block.index("2026-10-05"), block.index("2026-10-06")
    assert today < block.index("Intro chat") < tomorrow < block.index("Call with accountant"), block


def test_an_empty_tomorrow_is_said_and_an_empty_pair_costs_nothing(ag):
    _add(ag, "Intro chat", "2026-10-05", "16:15")
    block = ag.today_line()
    assert "2026-10-06" in block, "an empty tomorrow is an answer too"
    from widgets import store
    store.save("agenda", {"meetings": []})
    assert ag.today_line() == ""


def test_only_tomorrow_still_rides(ag):
    _add(ag, "Call with accountant", "2026-10-06", "10:00")
    assert "Call with accountant" in ag.today_line()
