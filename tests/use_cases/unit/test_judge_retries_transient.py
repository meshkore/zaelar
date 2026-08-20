"""Losing the verdict loses the whole ROUND, and that happened twice in a row.

On 2026-08-20 `book-hotel-night-known__es` was measured twice — two full eight-minute conversations, with
their mechanism report already built — and both were thrown away because the judge got `429 → 503` and
`429 → 504`. The fallback leg did not retry. Retrying costs one call; not retrying costs the run.

What is NOT retried: 401/402/404. That is balance or configuration, and retrying it only burns the clock.
"""
from __future__ import annotations

import pytest

from tests.voice.e2e.agent import llm as L


@pytest.fixture(autouse=True)
def _no_zai_and_no_sleep(monkeypatch):
    monkeypatch.setattr(L.config, "JUDGE_PROVIDER", "deepseek", raising=False)
    monkeypatch.setattr(L.config, "ZAI_KEY", "", raising=False)
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)


def test_a_503_is_retried_and_the_verdict_survives(monkeypatch):
    calls = {"n": 0}

    def _call(msgs, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("HTTP Error 503: Service Unavailable")
        return '{"ok":true}'

    monkeypatch.setattr(L, "call", _call)
    txt, model = L.judge_call([{"role": "user", "content": "x"}])
    assert txt == '{"ok":true}'
    assert calls["n"] == 3, "it did not retry: a whole round is lost to a 503"


def test_a_429_and_a_timeout_count_as_transient(monkeypatch):
    for err in ("HTTP Error 429: Too Many Requests", "socket timed out"):
        calls = {"n": 0}

        def _call(msgs, _e=err, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError(_e)
            return "{}"

        monkeypatch.setattr(L, "call", _call)
        L.judge_call([{"role": "user", "content": "x"}])
        assert calls["n"] == 2, f"\"{err}\" should have been retried"


def test_a_402_is_NOT_retried(monkeypatch):
    """Without this limit, an account with no balance costs three calls and 24 seconds for every case in the batch."""
    calls = {"n": 0}

    def _call(msgs, **kw):
        calls["n"] += 1
        raise RuntimeError("HTTP Error 402: Payment Required")

    monkeypatch.setattr(L, "call", _call)
    with pytest.raises(RuntimeError):
        L.judge_call([{"role": "user", "content": "x"}])
    assert calls["n"] == 1


def test_it_gives_up_after_three_and_raises_the_LAST_error(monkeypatch):
    def _call(msgs, **kw):
        raise RuntimeError("HTTP Error 503: Service Unavailable")

    monkeypatch.setattr(L, "call", _call)
    with pytest.raises(RuntimeError, match="503"):
        L.judge_call([{"role": "user", "content": "x"}])
