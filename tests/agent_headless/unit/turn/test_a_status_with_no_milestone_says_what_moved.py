"""A status with no milestone says the facts that moved, never one fixed line (three-tasks-at-once EN, 2026-10-15).

«under way, nothing new yet» was said for the game and the monitor turn after turn while both were working. With
no milestone to say, the line now carries its plan step, or how long it has been running — both from the live
record (`pending_summaries`), both different on the next ask.
"""
import pytest

from nucleo.turn import errands_of_a_turn as EOT


@pytest.fixture
def en(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")


def test_the_plan_step_is_said(en):
    assert EOT.errand_state({"done": 2, "total": 5, "secs": 300}) == "under way, on step 2 of 5"


def test_how_long_it_has_run_is_said_when_there_is_no_step(en):
    assert EOT.errand_state({"secs": 185}) == "under way for 3 min, no milestone yet"


def test_a_fresh_errand_keeps_the_plain_line(en):
    assert EOT.errand_state({"secs": 20}) == "under way, nothing new yet"


def test_the_live_record_carries_those_facts(monkeypatch):
    from nucleo import dispatch
    from nucleo.turn import named_errand
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [{"id": "t1", "request": "find a monitor", "secs": 200,
                                                                  "done": 1, "total": 4}])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: None)
    e = next(x for x in named_errand.known() if x["id"] == "t1")
    assert (e["secs"], e["done"], e["total"]) == (200, 1, 4)
