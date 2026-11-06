"""What the engine asks the outside world on a worker's behalf is ONE observer row each (capture gaps, 2026-11-06).

A worker's web search through our bridge left no row with what came back (only the CLI's own step), a page read none
at all, a question to the MeshKore network (the Oracle's search, an errand put to one agent) none, and a call routed
through mediated egress none. Now:

  · `search · 🔎 worker search` / `📄 worker read` — query or URL, route, source, count, ms and the EVIDENCE (titles,
    URLs, snippets within `observability/evidence`'s budget);
  · `mesh · 🌐 oracle · find` / `🌐 <agent> · ask` — intent, coverage, agents; status, ok, ms, a bounded scrubbed
    excerpt of the prompt and the answer, the NAMES of the structured fields, never a bearer;
  · `gateway · ↗ <family>` — the family and the path of a mediated call, never a credential; nothing in self-host.

Disarm: drop the `_record(` call from `web_search_bridge.run`, the `mesh_calls.asked` line from `mesh_agents.ask`, or
the `_record(` line from `egress.route_url` → red.
"""
from __future__ import annotations

import asyncio
import types

import pytest

from nucleo import mesh_agents
from nucleo.energy import egress
from nucleo.workers import web_search_bridge as bridge


@pytest.fixture
def rows(monkeypatch):
    out: list[dict] = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None: out.append(
        {"kind": kind, "label": label, "text": text, **(extra or {})}))
    bridge.forget()
    yield out
    bridge.forget()


def test_a_worker_search_leaves_its_evidence(rows, monkeypatch):
    import search
    from search.result import SearchResult
    from nucleo.workers import findings
    monkeypatch.setattr(findings, "hand_web_finding", lambda *a, **k: None)
    monkeypatch.setattr(findings, "hand_search_rows", lambda *a, **k: None)
    raw = {"query": "monitor 27", "answer": "", "source": "perplexity",
           "results": [{"title": "Monitor A", "url": "https://shop.example/a", "snippet": "189 EUR"}]}
    monkeypatch.setattr(search, "find", lambda *a, **k: SearchResult(query="monitor 27", route="fact", raw=raw))
    rec = types.SimpleNamespace(task_id="t-3", goal="a monitor")
    out = asyncio.run(bridge.run({"tool": "web_search", "args": {"query": "monitor 27"}}, rec))
    assert out["ok"] is True
    (r,) = [x for x in rows if x["kind"] == "search"]
    assert (r["label"], r["text"], r["id"], r["span"]) == ("🔎 worker search", "monitor 27", "t-3", "worker:t-3")
    assert r["source"] == "perplexity" and r["n"] == 1 and isinstance(r["ms"], int)
    assert r["evidence"]["items"][0]["u"] == "https://shop.example/a"


def test_an_oracle_search_and_an_agent_errand_are_one_row_each(rows, monkeypatch):
    def fake_post(url, body, timeout=0, bearer=None):
        if url.startswith(mesh_agents.ORACLE_URL):
            return 200, {"intent": "bookings.hotels", "coverage": "full", "agents": [
                {"agent_id": "roomrover", "endpoint": "https://rr.example", "online": True, "free": True}]}
        return 200, {"offers": [{"name": "Hotel Sol", "price": 90}]}
    monkeypatch.setattr(mesh_agents, "_post", fake_post)
    monkeypatch.setattr(mesh_agents, "_get", lambda url, timeout=0: None)          # no card fetch off the machine
    monkeypatch.setattr(mesh_agents, "_bearer_for", lambda agent, endpoint: "secret-bearer-xyz")
    monkeypatch.setattr(mesh_agents, "_is_live", lambda a, card=None: True)
    monkeypatch.setattr(mesh_agents, "_is_free", lambda a, card=None: True)
    found = mesh_agents.find("hotel en Madrid el 2026-12-01")
    mesh_agents.ask(found["agents"][0], "hotel en Madrid el 2026-12-01")
    mesh_agents.ask(found["agents"][0], "", fields={"city": "Madrid", "check_in": "2026-12-01"})
    f, a, b = [x for x in rows if x["kind"] == "mesh"]
    assert (f["label"], f["intent"], f["agents"], f["reached"]) == ("🌐 oracle · find", "bookings.hotels", ["roomrover"], True)
    assert a["label"] == "🌐 roomrover · ask · ✅" and a["status"] == 200 and "Hotel Sol" in a["answer"]
    assert a["text"].startswith("hotel en Madrid")
    assert b["fields"] == ["check_in", "city"] and b["text"] == "", "structured fields travel by NAME, never by value"
    assert all("secret-bearer-xyz" not in str(x) for x in rows), "the bearer never enters the record"


def test_a_mediated_call_is_one_gateway_row_and_self_host_records_nothing(rows, monkeypatch):
    monkeypatch.setattr(egress, "mediated", lambda: False)
    url = egress.base_of(egress._UPSTREAMS[0][0]) + "/search?q=x"
    assert egress.route_url(url, "k") == (url, "k")
    assert rows == []
    monkeypatch.setattr(egress, "mediated", lambda: True)
    monkeypatch.setenv("ZAELAR_GATEWAY_URL", "https://gw.example")
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", "tok-should-not-appear")
    egress.route_url(url, "k")
    (g,) = rows
    assert g["kind"] == "gateway" and g["family"] == egress._UPSTREAMS[0][0] and g["path"] == "/search" and g["ok"]
    assert "tok-should-not-appear" not in str(g)


def test_a_record_that_fails_never_takes_the_call_with_it(monkeypatch):
    import voice.observer as obs

    def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(obs, "emit", boom)
    monkeypatch.setattr(mesh_agents, "_post", lambda url, body, timeout=0, bearer=None: (200, {"ok": 1}))
    monkeypatch.setattr(mesh_agents, "_get", lambda url, timeout=0: None)
    monkeypatch.setattr(mesh_agents, "_bearer_for", lambda agent, endpoint: None)
    assert mesh_agents.ask({"agent_id": "x", "endpoint": "https://x.example"}, "hola")["ok"] is True
