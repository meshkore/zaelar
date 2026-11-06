"""A slow brief gets a second, identical request; the first answer wins (demo pass 2026-09-28, full18).

p50 317 ms, p90 450 ms, and 6 briefs in 78 hit the 2 s wall — each a turn with no verdict at all (C5b, E4 went
wrong that way). Passes 16-17 had none: a rare, long tail, which is what a hedged request is for."""

import pytest

from nucleo import jev


@pytest.fixture
def hedge_at_100ms(monkeypatch):
    monkeypatch.setenv("ZAELAR_JEV_HEDGE_MS", "100")


def test_the_brief_is_not_cut_before_its_readers_read_it(monkeypatch):
    """full24 A2: both hedged calls ran out at the 2 s wall and every later read saw «absent». The brief is read
    2-4 s after it is fired, so its deadline covers that window."""
    monkeypatch.delenv("ZAELAR_JEV_TIMEOUT_MS", raising=False)
    assert jev._timeout_s() >= 3.5
    assert jev._hedge_after_s() < jev._timeout_s() / 2
