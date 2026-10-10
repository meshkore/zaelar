"""The HTTP face of the search service (V2-782 T5.2): the same door for the turn, the worker and a curl."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from search import api as _api, health as _health, web


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(_api.router)
    monkeypatch.setattr(web, "search", lambda q, k=5, mode="answer": {
        "query": q, "answer": "", "source": "zai", "ai": False,
        "results": [{"title": "AOC U27B3A 152,99 €", "snippet": "", "url": "https://shop/aoc"}]})
    monkeypatch.setattr(_health, "probe_all", lambda names=None, parallel=True: [
        {"provider": "zai", "kind": "results", "paid": True, "key": "Z_AI_API_KEY", "ok": True, "latency_ms": 900,
         "state": "live", "why": ""}])
    _api._health_cache.update(at=0.0, rows=[])
    return TestClient(app)


def test_route_needs_no_network(client):
    r = client.post("/api/search/route", json={"query": "dame tres hoteles baratos", "proposal": "search_listings"})
    assert r.status_code == 200
    body = r.json()
    assert body["module"] == "listing" and body["breadth"]["n_final"] == 3 and body["fields"] == ["price"]


def test_find_returns_the_one_shape(client):
    r = client.post("/api/search/find", json={"query": "monitor 27 4K", "route": "inline_fact", "k": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["n"] == 1 and body["route"] == "inline_fact" and body["provider"] == "zai"
    assert body["candidates"][0]["price"] == "152,99 €"
    assert set(body) >= {"candidates", "pages", "sources", "criteria", "unshown", "needs", "failure", "took_ms"}


def test_health_is_cached_and_fresh_refreshes(client, monkeypatch):
    r = client.get("/api/search/health")
    assert r.status_code == 200 and r.json()["summary"]["can_answer"]
    monkeypatch.setattr(_health, "probe_all", lambda names=None, parallel=True: [])
    assert client.get("/api/search/health").json()["providers"], "within the TTL the cached rows are served"
    assert client.get("/api/search/health?fresh=1").json()["providers"] == []


def test_the_router_is_mounted_by_the_server():
    src = (__import__("pathlib").Path(__file__).resolve().parents[3] / "server" / "__init__.py").read_text(encoding="utf-8")
    assert "from search.api import router as search_router" in src
