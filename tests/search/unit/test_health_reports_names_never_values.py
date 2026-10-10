"""The health probe says live · missing · exhausted · blocked · credential, with key NAMES and never values (V2-782 T2.1).

A missing key is MISSING, not down: the fix is a key, not a bug. Foursquare's real answer on 2026-10-10 («no API
credits remaining», HTTP 429) must read as `exhausted`, and the Z.ai coding plan's «Weekly/Monthly Limit
Exhausted» would too.
"""
from __future__ import annotations

import json

import pytest

from search import health
from search.providers import PROVIDERS

SECRET = "sk-THIS-VALUE-MUST-NEVER-BE-PRINTED-0123456789"


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setenv("Z_AI_API_KEY", SECRET)
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    monkeypatch.setenv("FOURSQUARE_SERVICE_KEY", SECRET)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("PPLX_API_KEY", raising=False)


def test_a_missing_key_is_missing_not_down(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    row = health.probe("tavily")
    assert row["state"] == "missing" and row["key"] == "TAVILY_API_KEY" and not row["ok"]


def test_the_switch_off_is_off(monkeypatch):
    monkeypatch.setenv("BROWSER_SEARCH", "0")
    assert health.probe("google")["state"] == "off"


@pytest.mark.parametrize("detail,state", [
    ("RuntimeError: foursquare places: HTTP 429 {\"message\": \"Your account has no API credits remaining\"}", "exhausted"),
    ("Weekly/Monthly Limit Exhausted, reset 2026-10-30", "exhausted"),
    ("HTTP 401 API key not valid", "credential"),
    ("captcha: DuckDuckGo served an anti-bot challenge («made by a human»)", "blocked"),
    ("google: bloqueado (captcha/tráfico inusual)", "blocked"),
    ("ReadTimeout: timed out", "network"),
    ("KeyError: 'results'", "down"),
])
def test_failures_are_classified_by_what_the_provider_said(detail, state):
    assert health.classify(detail) == state


def test_a_failing_call_reports_its_state_and_a_live_one_its_latency(keyed, monkeypatch):
    def fake_call(name):
        if name == "foursquare":
            raise RuntimeError("foursquare places: HTTP 429 Your account has no API credits remaining")
        if name == "zai":
            return True, ""
        if name == "gemini":
            raise RuntimeError("HTTP 403 PERMISSION_DENIED")
        raise AssertionError(name)

    monkeypatch.setattr(health, "_call", fake_call)
    rows = health.probe_all(["foursquare", "zai", "gemini"], parallel=False)
    by = {r["provider"]: r for r in rows}
    assert by["foursquare"]["state"] == "exhausted" and by["foursquare"]["key"] == "FOURSQUARE_SERVICE_KEY"
    assert by["zai"]["state"] == "live" and by["zai"]["ok"]
    assert by["gemini"]["state"] == "credential"
    s = health.summary(rows)
    assert s["live"] == ["zai"] and s["can_answer"] and s["can_discover"] and not s["can_place"]
    assert [f["provider"] for f in s["failing"]] == ["foursquare", "gemini"]
    text = health.render(rows) + json.dumps(rows)
    assert SECRET not in text, "a key VALUE reached a report"
    assert "FOURSQUARE_SERVICE_KEY" in text


def test_the_browser_probes_say_they_need_the_engine_outside_it(monkeypatch):
    monkeypatch.delenv("BROWSER_SEARCH", raising=False)
    from search import browser
    monkeypatch.setattr(browser, "_loop", None)
    assert health.probe("google")["state"] == "engine"
    assert health.probe("images")["state"] == "engine"


def test_no_live_provider_means_the_harness_may_not_grade(monkeypatch):
    monkeypatch.setattr(health, "_call", lambda name: (_ for _ in ()).throw(RuntimeError("HTTP 429 quota")))
    for k in ("Z_AI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(k, SECRET)
    rows = health.probe_all(["zai", "gemini", "ddg"], parallel=False)
    assert not health.summary(rows)["can_answer"]
    assert "INFRA" in health.render(rows)


def test_every_declared_provider_has_a_probe(monkeypatch):
    """A provider without a probe would be `down` forever, which is the lie this module exists to stop."""
    import inspect
    src = inspect.getsource(health._call)
    for name in PROVIDERS:
        assert f'"{name}"' in src, f"no probe branch for {name}"
