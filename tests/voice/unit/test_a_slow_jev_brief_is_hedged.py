"""A slow brief gets a second, identical request; the first answer wins (demo pass 2026-09-28, full18).

p50 317 ms, p90 450 ms, and 6 briefs in 78 hit the 2 s wall — each a turn with no verdict at all (C5b, E4 went
wrong that way). Passes 16-17 had none: a rare, long tail, which is what a hedged request is for."""
import threading
import time

import pytest

from nucleo import jev


@pytest.fixture
def hedge_at_100ms(monkeypatch):
    monkeypatch.setenv("ZAELAR_JEV_HEDGE_MS", "100")


def test_a_stuck_first_call_is_overtaken_by_the_hedge(hedge_at_100ms, monkeypatch):
    calls = []

    def post(state, questions, timeout_s):
        n = len(calls)
        calls.append(n)
        if n == 0:
            time.sleep(1.5)                    # the provider's tail
            return {"who": "first"}
        return {"who": "hedge"}
    monkeypatch.setattr(jev, "_post_many", post)
    t0 = time.monotonic()
    got = jev._post_many_hedged("s", {"q": {}}, 2.0)
    assert got == {"who": "hedge"} and time.monotonic() - t0 < 0.8 and len(calls) == 2


def test_a_quick_first_call_sends_no_second(hedge_at_100ms, monkeypatch):
    calls = []
    monkeypatch.setattr(jev, "_post_many", lambda s, q, t: calls.append(1) or {"who": "first"})
    assert jev._post_many_hedged("s", {"q": {}}, 2.0) == {"who": "first"} and len(calls) == 1


def test_both_failing_still_fails_like_one_call(hedge_at_100ms, monkeypatch):
    def post(state, questions, timeout_s):
        time.sleep(0.2)
        raise TimeoutError("The read operation timed out")
    monkeypatch.setattr(jev, "_post_many", post)
    with pytest.raises(TimeoutError):
        jev._post_many_hedged("s", {"q": {}}, 0.5)


def test_the_brief_goes_through_the_hedge():
    import inspect
    assert "_post_many_hedged(state, questions" in inspect.getsource(jev.choose_many_sync)


def test_the_brief_is_not_cut_before_its_readers_read_it(monkeypatch):
    """full24 A2: both hedged calls ran out at the 2 s wall and every later read saw «absent». The brief is read
    2-4 s after it is fired, so its deadline covers that window."""
    monkeypatch.delenv("ZAELAR_JEV_TIMEOUT_MS", raising=False)
    assert jev._timeout_s() >= 3.5
    assert jev._hedge_after_s() < jev._timeout_s() / 2
