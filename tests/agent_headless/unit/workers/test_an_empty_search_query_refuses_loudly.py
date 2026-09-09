# V2-644 — the web_search bridge refuses an EMPTY query instead of echoing an empty result.
#
# Measured 2026-09-09 (the Juncal research): the worker asked for `use_tool web_search` with its query under a
# key the gate did not read, got `{"results": [], "source": "none"}` back twice, concluded «the search bridge
# returns nothing» and drove the browser for four minutes instead. The silent echo blamed the MODULE; only an
# error naming the key could have said the real fault was the payload shape.
import asyncio

import pytest

from nucleo import worker_api


class _Rec:
    task_id = "t1"
    goal = "test"


def _run(payload):
    return asyncio.run(worker_api._exec_allow("use_tool", payload, _Rec()))


def test_an_empty_query_refuses_and_names_the_key():
    out = _run({"tool": "web_search", "args": {}})
    assert out.get("ok") is False
    assert "query" in (out.get("error") or ""), out
    # The error carries the exact working form — same contract as node 4.20: a failure says how to get out.
    assert '"args"' in out["error"] and "web_search" in out["error"]


def test_a_query_under_a_sibling_key_still_searches(monkeypatch):
    """Forgiving on the key, strict on the emptiness: `q`, `text`, `search` and `consulta` are the shapes a
    worker actually writes, and all of them must reach the engine's search — not come back empty."""
    seen = []
    monkeypatch.setattr("nucleo.websearch.search", lambda q, *a, **k: seen.append(q) or
                        {"query": q, "answer": "", "results": [], "source": "test", "ai": False})
    for key in ("query", "q", "text", "search", "consulta"):
        out = _run({"tool": "web_search", "args": {key: f"empresa {key}"}})
        assert out.get("ok") is True, (key, out)
    assert seen == [f"empresa {k}" for k in ("query", "q", "text", "search", "consulta")]


def test_the_canonical_top_level_query_still_works(monkeypatch):
    monkeypatch.setattr("nucleo.websearch.search", lambda q, *a, **k:
                        {"query": q, "answer": "", "results": [], "source": "test", "ai": False})
    out = _run({"tool": "web_search", "query": "Juncadella Salvador SL"})
    assert out.get("ok") is True
    assert out["result"]["query"] == "Juncadella Salvador SL"


def test_whitespace_is_still_empty():
    out = _run({"tool": "web_search", "args": {"query": "   "}})
    assert out.get("ok") is False
