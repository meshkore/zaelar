"""A transient rate limit is waited out, a bounded few seconds, before a build is declared dead.

Measured 2026-10-10 20:54 (use case `build-workout-tracker-widget__us`): the widget agent's CLI exited 1 with
«API Error: Request rejected (429) · [1302][Rate limit reached for requests]» (Z.ai, Anthropic-compatible
endpoint), seven seconds in. `providers.note_failure` returns no cause for a rate limit — on purpose, a healthy
tier is not put on cooldown — so the generator's ladder had nothing to relay to and the build died on the first
blip: worker_health spawned=1, ok=0, errored=1. Only `rate` is retried: quota/credit, a rejected key and a bad
request fail the same way a second later, and retrying them burns the operator's wait.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from nucleo.workers import rate_retry
from widgets import generator

Z_AI_1302 = "API Error: Request rejected (429) · [1302][Rate limit reached for requests][20261011025437c9]"


@pytest.mark.parametrize("text", [Z_AI_1302, "429 Too Many Requests", "rate limit reached, slow down",
                                  "agent failed [rate]: API Error: Request rejected (429) · [1302]"])
def test_a_transient_rate_limit_is_retryable(text):
    assert rate_retry.is_transient(text)


@pytest.mark.parametrize("text", [
    "402 Payment Required: insufficient balance",
    '{"error":{"message":"Insufficient Balance"}}',
    "API Error: Request rejected (429) · [1310][Weekly/Monthly Limit Exhausted. Your limit will reset at 2026-10-12",
    "Usage limit reached for 5 hour. Your limit will reset at 22:00",
    "HTTP 401 Unauthorized", "Invalid API key · Please run /login", "403 Forbidden",
    "API Error: 400 bad request: invalid parameter", "TypeError: cannot read the manifest", "", "the agent timed out",
])
def test_quota_auth_and_bad_requests_are_not_retried(text):
    assert not rate_retry.is_transient(text)


def test_the_backoff_is_jittered_exponential_and_bounded():
    lo = rate_retry.delays(3, base=4, cap_total=100, rng=lambda: 0.0)
    hi = rate_retry.delays(3, base=4, cap_total=100, rng=lambda: 1.0)
    assert lo == [3.0, 6.0, 12.0] and hi == [5.0, 10.0, 20.0]
    capped = rate_retry.delays(5, base=4, cap_total=20, rng=lambda: 0.5)
    assert sum(capped) <= 20.0 and capped[0] == 4.0
    # the shipped schedule fits a voice errand: a couple of retries, well under half a minute of waiting
    assert 1 <= len(rate_retry.delays()) <= 3 and sum(rate_retry.delays()) <= rate_retry.RATE_RETRY_MAX_TOTAL_S <= 30


class _Script:
    """A fake `claude` CLI: each spawn pops the next outcome (an error text, or None for success)."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.spawned = 0
        script = self

        class _P:
            def __init__(self, *a, **k):
                script.spawned += 1
                self._err = script.outcomes.pop(0) if script.outcomes else None
                self.returncode = 1 if self._err else 0

            def communicate(self, input=None, timeout=None):  # noqa: A002
                if self._err:
                    return '{"is_error":true,"result":%s}' % __import__("json").dumps(self._err), ""
                return '{"result":"DONE"}', ""

            def poll(self):
                return self.returncode
        self.Popen = _P


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(generator, "_find_claude", lambda: "/usr/bin/claude")
    monkeypatch.setattr(rate_retry, "RATE_RETRY_BASE_S", 0.01)
    from nucleo.workers import providers
    monkeypatch.setattr(providers, "note_failure", lambda *a, **k: None)

    def _install(outcomes):
        s = _Script(outcomes)
        monkeypatch.setattr(generator.subprocess, "Popen", s.Popen)
        return s
    return _install


def test_a_build_that_hits_a_rate_limit_is_retried_and_lands(cli, tmp_path):
    s = cli([Z_AI_1302, Z_AI_1302, None])
    ran, err = generator._run_agent("build it", "tok-1", target=str(tmp_path))
    assert ran is True and err == ""
    assert s.spawned == 3


def test_the_retries_are_bounded_and_the_death_keeps_its_class(cli, tmp_path):
    s = cli([Z_AI_1302] * 10)
    ran, err = generator._run_agent("build it", "tok-2", target=str(tmp_path))
    assert ran is False and generator.failure_class(err) == "rate"
    assert s.spawned == 1 + rate_retry.RATE_RETRIES


@pytest.mark.parametrize("text,cls", [("402 Payment Required: insufficient balance", "credit"),
                                      ("HTTP 401 Unauthorized", "auth"),
                                      ("TypeError: cannot read the manifest", "ours")])
def test_credit_auth_and_our_own_bugs_are_not_retried(cli, tmp_path, text, cls):
    s = cli([text, None, None])
    ran, err = generator._run_agent("build it", "tok-3", target=str(tmp_path))
    assert ran is False and generator.failure_class(err) == cls
    assert s.spawned == 1, f"a {cls} failure was retried"


def test_a_stop_during_the_wait_is_honoured(cli, monkeypatch, tmp_path):
    monkeypatch.setattr(rate_retry, "RATE_RETRY_BASE_S", 2.0)
    s = cli([Z_AI_1302, None])
    threading.Timer(0.3, lambda: generator.kill("tok-4")).start()
    t0 = time.monotonic()
    ran, err = generator._run_agent("build it", "tok-4", target=str(tmp_path))
    assert ran is False and err == "generation cancelled"
    assert s.spawned == 1 and time.monotonic() - t0 < 1.5


def _rec(summary, **kw):
    from nucleo.workers.session import SessionRecord
    rec = SessionRecord(task_id="w1", goal="find me a flat in Madrid", kind="web")
    rec.ok, rec.status, rec.result_summary = False, "running", summary
    for k, v in kw.items():
        setattr(rec, k, v)
    return rec


def test_a_brain_worker_that_died_on_a_rate_limit_is_relaunched_once_after_a_wait(monkeypatch):
    from nucleo.flash import escalate
    sent = []
    monkeypatch.setattr(escalate, "escalate_to_slowbrain", lambda req, context=None: sent.append((req, context)) or 7)
    planned = []
    rec = _rec(Z_AI_1302)
    assert rate_retry.relaunch_after_rate(rec, 2, schedule=lambda wait, fn: planned.append((wait, fn)))
    assert len(planned) == 1 and 0 < planned[0][0] <= rate_retry.RATE_RETRY_MAX_TOTAL_S
    assert rec.handoff and rec.result_summary == "" and rec.ok is False     # relayed, not delivered as a death
    planned[0][1]()
    assert sent == [("find me a flat in Madrid", sent[0][1])]
    assert sent[0][1]["relay_gen"] == 1 and sent[0][1]["src"] == "provider_failover"


@pytest.mark.parametrize("summary,kw", [
    ("402 Payment Required: insufficient balance", {}),
    ("HTTP 401 Unauthorized", {}),
    (Z_AI_1302, {"relay_gen": 2}),                                         # the chain's cap still binds
    (Z_AI_1302, {"status": "cancelled"}),
    ("No pude crear el widget — el proveedor está saturado, prueba en un momento.", {}),   # generator already waited
])
def test_a_brain_worker_is_not_relaunched_for_anything_else(summary, kw):
    rec = _rec(summary, **kw)
    assert not rate_retry.relaunch_after_rate(rec, 2, schedule=lambda *a: pytest.fail("relaunched"))
    assert rec.handoff == ""


def test_the_relay_ladder_runs_the_rate_lane_on_the_loop(monkeypatch):
    """Through the real entry point `_finish` calls, with the real scheduler (the loop's `call_later`)."""
    from nucleo.flash import escalate
    from nucleo.workers.relay import relay_out_of_fuel
    monkeypatch.setattr(rate_retry, "RATE_RETRY_BASE_S", 0.01)
    sent = []
    monkeypatch.setattr(escalate, "escalate_to_slowbrain", lambda req, context=None: sent.append(req) or 7)
    rec = _rec(Z_AI_1302)

    async def _run():
        relay_out_of_fuel(rec, 2)
        await asyncio.sleep(0.2)
    asyncio.run(_run())
    assert sent == ["find me a flat in Madrid"] and rec.handoff
