"""No unit test may write to the campaign's LIVE artifacts.

Written on 2026-08-20 after finding the reason for an anomaly that had gone unexplained for a day: the loop
log showed «ticks» at 02:46, 10:19, 10:24, and 10:25 that classified a case as BLOCKED with timestamps
from the past (`'01:00'→'02:20'`), and no tick process was running. They were not ticks: it was
`test_blocked_filing.py` calling `_retest_pending()` without intercepting `_log`, so **every run of the unit
test suite wrote to the log read by the operator** — with the times from its simulated ledger.

The damage is the kind that is difficult to find: the loop log is the only evidence of what was measured and
when, and a few false lines there do not break anything; they only make the evidence lie. It is fixed in the
CONFTEST rather than test by test, because the next test that called a tick function would do it again
without anyone noticing.
"""
from __future__ import annotations

import pytest

from tests.use_cases.e2e.agent import status as statusmod, tick as T


_LIVE_LEDGER = statusmod.LEDGER_PATH
_LIVE_BOARD = statusmod.BOARD_PATH


@pytest.fixture(autouse=True)
def _never_touch_live_artifacts(tmp_path, monkeypatch):
    """By default, EVERYTHING points to a temporary directory. The tick log has no possible exception."""
    monkeypatch.setattr(T, "LOG_PATH", tmp_path / "tick.log")
    monkeypatch.setattr(statusmod, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(statusmod, "BOARD_PATH", tmp_path / "STATUS.md")
    yield


@pytest.fixture
def live_board(monkeypatch):
    """EXPLICIT opt-in for the few tests that assert an invariant of the REAL board (e.g. «no case that has
    already been judged remains in the queue»). Returns the real paths, for READING only.

    It is intentionally opt-in rather than the opposite: a test that forgets to isolate itself cannot write to
    the live artifacts again, and a test that needs the real board has to say so in its signature, where it is
    visible.
    """
    monkeypatch.setattr(statusmod, "LEDGER_PATH", _LIVE_LEDGER)
    monkeypatch.setattr(statusmod, "BOARD_PATH", _LIVE_BOARD)
    return _LIVE_LEDGER
