"""The numbers that decide WHOSE fault a defect is have to be in the file the fixing agent opens.

Until 2026-08-21 every one of them was pulled out by hand with a throwaway script and pasted into a
cluster message. That works while somebody is sitting there doing it, and does not survive a handover:
the .md report — the thing another agent actually reads — carried none of them.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent.report import _mechanism_numbers as M


def test_a_quiet_healthy_round_says_nothing():
    """No line without something to say: a report padded with zeroes stops being read."""
    assert M({}) == []
    assert M({"worker_health": {"spawned": 0}, "search_returns": {"queries": 0}}) == []


def test_a_relay_is_named_as_NOT_a_death():
    out = " ".join(M({"worker_health": {"spawned": 3, "ok": 1, "errored": 0, "relayed": 1,
                                        "still_running": 1}}))
    assert "NO es una muerte" in out
    assert "seguía(n) trabajando" in out


def test_the_shared_session_carries_its_own_contrast():
    out = " ".join(M({"worker_deaths": {"shared_sessions": {"c5ad1d9e": ["3", "4"]},
                                        "dead_resuming": 2, "resuming": 2,
                                        "dead_fresh": 0, "fresh": 3, "lifetimes_ms": {}}}))
    assert "COMPARTIDA" in out
    assert "2 de 2" in out and "0 de 3" in out, "the split IS the finding; a count of corpses is not"


def test_a_search_that_answered_and_never_arrived_is_flagged():
    out = " ".join(M({"search_returns": {"queries": 23, "returns": 22, "notes_from_search": 0}}))
    assert "NINGUNA se le empujó al cerebro" in out


def test_and_is_NOT_flagged_when_it_did_arrive():
    out = " ".join(M({"search_returns": {"queries": 5, "returns": 5, "notes_from_search": 5}}))
    assert "NINGUNA" not in out


def test_an_unsettled_round_warns_that_missing_may_mean_not_yet():
    out = " ".join(M({"quiescence": {"settled": False, "waited_s": 60.2, "pending_workers": 1}}))
    assert "todavía no" in out


def test_a_settled_round_says_nothing_about_it():
    assert M({"quiescence": {"settled": True, "waited_s": 6.0, "pending_workers": 0}}) == []
