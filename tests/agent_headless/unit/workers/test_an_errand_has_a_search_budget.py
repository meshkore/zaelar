"""One errand may run a bounded number of web searches; spent, the worker is told to deliver (node 2.749).

Audit V2-783 P1-6: search slowness was the judge's first family and nothing bounded a worker's query loop. Measured
over 190 recorded errands: median 6 queries, p90 29, p95 38, max 61 — the bound sits at the p95.
"""
from __future__ import annotations

import asyncio
import types

import pytest

from nucleo.cli import worker_api
from nucleo.workers import search_budget


@pytest.fixture(autouse=True)
def _clean():
    search_budget.forget()
    yield
    search_budget.forget()


def test_the_budget_holds_the_tail_and_never_the_normal_hunt():
    assert all(search_budget.spend("t-1") == "" for _ in range(search_budget.MAX_QUERIES))
    assert "deliver now" in search_budget.spend("t-1")
    assert search_budget.spend("t-2") == "", "another errand has its own budget"
    assert 29 <= search_budget.MAX_QUERIES <= 61, "the bound is the measured p95, not a taste"


def test_a_spent_budget_reaches_the_worker_without_searching(monkeypatch):
    import search
    calls = []
    monkeypatch.setattr(search, "find", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(RuntimeError("x")))
    rec = types.SimpleNamespace(task_id="t-9", goal="a monitor")
    for _ in range(search_budget.MAX_QUERIES):
        search_budget.spend("t-9")
    out = asyncio.run(worker_api._exec_allow("use_tool", {"tool": "web_search", "args": {"query": "monitor"}}, rec))
    assert out["ok"] is False and "budget" in out["error"] and calls == []
