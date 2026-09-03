"""server/config_api.py::get_connector_catalog (V2-561) — GET /api/connectors/catalog serves the NOT-live

half of the connector directory (planned/not-possible) for the ChatWall "Conectores" tab's wishlist.
`GET /api/connectors` (registry.py, unchanged by this pass) stays the live half; this endpoint must never
leak a `built` entry into its response — the frontend trusts that split to decide which list a row came
from without re-checking `state` itself.
"""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.config_api import router


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_the_catalog_route_serves_only_planned_and_not_possible(tmp_path, monkeypatch):
    from connectors import catalog
    monkeypatch.setattr(catalog, "_DIR", tmp_path)
    (tmp_path / "built.json").write_text(
        json.dumps({"id": "b", "label": "B", "family": "infra", "state": "built", "capabilities": ["b"]}),
        encoding="utf-8")
    (tmp_path / "planned.json").write_text(
        json.dumps({"id": "p", "label": "P", "family": "infra", "state": "planned", "capabilities": ["p"]}),
        encoding="utf-8")

    r = _client().get("/api/connectors/catalog")
    assert r.status_code == 200
    body = r.json()
    ids = {m["id"] for m in body["catalog"]}
    assert ids == {"p"}, "a built entry leaked into the wishlist route"


def test_the_catalog_route_fails_open_on_a_broken_catalog_module(monkeypatch):
    """A wishlist that cannot load must degrade to empty, never 500 the whole ChatWall tab."""
    import connectors.catalog as catalog_mod

    def _boom():
        raise RuntimeError("disk unavailable")
    monkeypatch.setattr(catalog_mod, "wishlist", _boom)
    r = _client().get("/api/connectors/catalog")
    assert r.status_code == 200
    assert r.json()["catalog"] == []


def test_the_live_connectors_route_is_unaffected():
    """Sanity: this pass did not touch GET /api/connectors itself."""
    r = _client().get("/api/connectors")
    assert r.status_code == 200
    assert "connectors" in r.json()
