"""V2-798 — a network agent's timeout is a property of the AGENT, the call has ONE budget, only operational agents
are asked, and an empty answer with the agent's own hint is an answer.

Measured across sessions 2026-09-25 → 2026-10-26: «The read operation timed out» against five different agents
(hotels, flights, tradespeople, wellness, restaurants) with a fixed 12 s skill timeout — and the restaurant agent,
timed from outside, answers in 14.2 s. Every one of those answers was reported to the worker as «the agents did not
answer», and the errand went to a browser that met a 403.

Each guard below carries its disarm. Domain-free: the agents are named a, b, c.
"""
from __future__ import annotations

import pytest

from nucleo import mesh_agents as m
from nucleo.workers import source_outcomes as so

MEASURED_LATENCY_S = 14.2

A = {"agent_id": "agent-a", "endpoint": "https://a.example", "online": True, "operational": True,
     "pricing": {"amount": 0, "currency": "free"}}
B = {"agent_id": "agent-b", "endpoint": "https://b.example", "online": True,
     "pricing": {"amount": 0, "currency": "free"}}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    so.forget()
    m._cards.clear()
    monkeypatch.setattr(m, "_get", lambda url, timeout=None: None)
    try:
        from nucleo import workflows
        monkeypatch.setattr(workflows, "plan", lambda *a, **k: None)
    except Exception:
        pass
    yield
    so.forget()
    m._cards.clear()


# ── the timeout belongs to the agent ──────────────────────────────────────────────────────────────────────────

def test_an_agent_that_declares_nothing_gets_a_generous_floor():
    assert m.agent_timeout(A) >= 60.0 > MEASURED_LATENCY_S * 4


def test_a_declared_latency_is_kept_with_headroom_and_bounded():
    assert m.agent_timeout({**A, "latency_ms": 40_000}) == 80.0
    assert m.agent_timeout({**A, "operational": {"p95_ms": 10_000}}) == 60.0      # never below the floor
    assert m.agent_timeout({**A, "expected_latency_s": 600}) == m._SERVE_CAP_S    # never above the cap


def test_ask_waits_what_the_agent_needs(monkeypatch):
    seen = {}
    monkeypatch.setattr(m, "_post", lambda url, body, timeout=None: (seen.update(t=timeout) or (200, {"count": 3})))
    assert m.ask(A, "a table for two")["ok"]
    assert seen["t"] >= 60.0


def test_disarmed_a_floor_at_the_old_guess_times_out_a_real_agent(monkeypatch):
    """RED proof: with the floor back at the old 12 s, the measured 14.2 s agent is beyond the wait."""
    saved = m._SERVE_FLOOR_S
    try:
        m._SERVE_FLOOR_S = 12.0
        assert m.agent_timeout(A) < MEASURED_LATENCY_S
    finally:
        m._SERVE_FLOOR_S = saved
    assert m.agent_timeout(A) > MEASURED_LATENCY_S


# ── a timeout is named and recorded ───────────────────────────────────────────────────────────────────────────

def test_a_transport_timeout_is_told_apart_from_a_refusal(monkeypatch):
    import urllib.request

    def _slow(req, timeout=None):
        raise TimeoutError("The read operation timed out")
    monkeypatch.setattr(urllib.request, "urlopen", _slow)
    assert m._post("https://a.example/v1/x", {}) == (0, {"transport": "timeout"})

    def _refused(req, timeout=None):
        raise ConnectionRefusedError("refused")
    monkeypatch.setattr(urllib.request, "urlopen", _refused)
    assert m._post("https://a.example/v1/x", {}) == (0, None)


def test_a_timed_out_agent_is_named_and_remembered(monkeypatch):
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "x", "agents": [A], "reached": True})
    monkeypatch.setattr(m, "_post", lambda url, body, timeout=None: (0, {"transport": "timeout"}))
    out = m.serve("a table for two on Monday", "a table for two on 2026-10-26 14:00")
    assert not out["ok"] and out.get("timed_out") and "agent-a" in out["reason"] and " s" in out["reason"]
    assert so.verdict("agent-a")["outcome"] == so.TIMEOUT


# ── one budget, not one wait per candidate ────────────────────────────────────────────────────────────────────

class _Clock:
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t


def test_a_second_candidate_gets_only_what_is_left_of_the_budget(monkeypatch):
    clock, asked = _Clock(), []
    monkeypatch.setattr(m.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "x", "agents": [A, B], "reached": True})

    def _ask(agent, prompt, fields=None, timeout=None):
        asked.append((agent["agent_id"], timeout))
        clock.t += timeout                                     # it used its whole wait
        return {"ok": False, "timed_out": True, "waited_s": round(timeout), "agent": agent["agent_id"]}
    monkeypatch.setattr(m, "ask", _ask)
    m.serve("errand", "errand")
    assert asked[0] == ("agent-a", 60.0)
    assert asked[1][0] == "agent-b" and asked[1][1] == pytest.approx(m._SERVE_BUDGET_S - 60.0)
    assert sum(t for _, t in asked) <= m._SERVE_BUDGET_S


def test_no_second_candidate_when_the_budget_is_spent(monkeypatch):
    clock, asked = _Clock(), []
    monkeypatch.setattr(m.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "x", "agents": [{**A, "latency_ms": 45_000}, B],
                                                     "reached": True})

    def _ask(agent, prompt, fields=None, timeout=None):
        asked.append(agent["agent_id"])
        clock.t += timeout
        return {"ok": False, "timed_out": True, "waited_s": round(timeout)}
    monkeypatch.setattr(m, "ask", _ask)
    m.serve("errand", "errand")
    assert asked == ["agent-a"]          # 90 s spent, 10 s left: below the minimum worth starting


def test_disarmed_without_the_budget_the_wait_doubles(monkeypatch):
    """RED proof: with an unbounded budget, two slow candidates cost two full waits."""
    clock, asked = _Clock(), []
    monkeypatch.setattr(m.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "x", "agents": [A, B], "reached": True})

    def _ask(agent, prompt, fields=None, timeout=None):
        asked.append(timeout)
        clock.t += timeout
        return {"ok": False, "timed_out": True, "waited_s": round(timeout)}
    monkeypatch.setattr(m, "ask", _ask)
    monkeypatch.setattr(m, "_SERVE_BUDGET_S", 10 ** 6)
    m.serve("errand", "errand")
    assert sum(asked) > 100.0


def test_an_agent_that_failed_lately_is_asked_after_the_others_never_dropped(monkeypatch):
    so.note("agent-a", so.TIMEOUT, kind="agent")
    order = []
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "x", "agents": [A, B], "reached": True})
    monkeypatch.setattr(m, "ask", lambda agent, prompt, fields=None, timeout=None: (
        order.append(agent["agent_id"]) or {"ok": False, "status": 500, "asks": {}}))
    m.serve("errand", "errand")
    assert order == ["agent-b", "agent-a"]


# ── only operational agents ───────────────────────────────────────────────────────────────────────────────────

def test_the_oracle_saying_not_operational_keeps_the_agent_out(monkeypatch):
    down = {**B, "agent_id": "agent-c", "operational": False}
    monkeypatch.setattr(m, "_post", lambda url, body, timeout=None: (200, {"intent": "x", "agents": [A, down]}))
    found = m.find("errand")
    assert [a["agent_id"] for a in found["agents"]] == ["agent-a"] and found["not_live"] == ["agent-c"]


def test_silence_about_operational_is_not_a_statement(monkeypatch):
    monkeypatch.setattr(m, "_post", lambda url, body, timeout=None: (200, {"intent": "x", "agents": [B]}))
    assert [a["agent_id"] for a in m.find("errand")["agents"]] == ["agent-b"]


def test_a_card_that_says_not_available_now_is_not_live():
    assert not m._is_live(A, {"availability": {"now": False}})
    assert m._is_live(A, {"availability": {"now": True}})


def test_a_learned_route_to_an_agent_the_oracle_calls_down_is_skipped(monkeypatch):
    asked = []
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "bookings.x", "agents": [B], "reached": True,
                                                     "not_live": ["agent-a"]})
    monkeypatch.setattr(m, "route_for", lambda intent: A)
    monkeypatch.setattr(m, "ask", lambda agent, prompt, fields=None, timeout=None: (
        asked.append(agent["agent_id"]) or {"ok": True, "data": {"count": 2, "items": [1, 2]}}))
    assert m.serve("errand", "errand")["agent"] == "agent-b" and asked == ["agent-b"]


def test_disarmed_reading_only_the_heartbeat_lets_a_broken_agent_in(monkeypatch):
    """RED proof: `online` alone is a heartbeat; ignoring `operational` would ask an agent whose skills fail."""
    down = {**B, "operational": False}
    real = m._is_live
    monkeypatch.setattr(m, "_is_live", lambda agent, card=None: agent.get("online") is not False)
    monkeypatch.setattr(m, "_post", lambda url, body, timeout=None: (200, {"intent": "x", "agents": [down]}))
    assert m.find("errand")["agents"], "the disarm did not land"
    monkeypatch.setattr(m, "_is_live", real)
    assert not m.find("errand")["agents"]


# ── an empty answer with a hint is an answer ──────────────────────────────────────────────────────────────────

def test_zero_rows_with_the_agents_hint_comes_back_as_an_answer(monkeypatch):
    monkeypatch.setattr(m, "find", lambda q, **k: {"intent": "x", "agents": [A], "reached": True})
    monkeypatch.setattr(m, "_post", lambda url, body, timeout=None: (
        200, {"count": 0, "results": [], "hint": "widen radius_m or pass lat/lon"}))
    out = m.serve("errand", "errand")
    assert out["ok"] is True and out["empty"] is True
    assert out["agent_hint"] == "widen radius_m or pass lat/lon" and "agent_hint" in out["reason"]
    v = so.verdict("agent-a")
    assert v["outcome"] == so.EMPTY and "radius" in v["detail"]


def test_rows_are_recorded_as_served(monkeypatch):
    monkeypatch.setattr(m, "_post", lambda url, body, timeout=None: (200, {"count": 1, "results": [{"name": "x"}]}))
    assert m.ask(A, "errand")["ok"]
    assert so.verdict("agent-a")["outcome"] == so.SERVED
