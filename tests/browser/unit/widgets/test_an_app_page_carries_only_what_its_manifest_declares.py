"""V2-823 — an app's PAGE (`widgets/about.py`) carries only what its manifest declares.

The apps window paints whatever `/widgets/<id>/about` returns, so this is where «never invent a field» is decided:
a manifest without `owner` / `created` / `licence` / `connector_families` yields a page without those keys — not an
empty string, not «unknown». The connectors a page lists are the LIVE inventory read with the one `serves()` reader,
so a source that serves the family through `families` (Telegram in Contacts) is listed too. And the shipped apps now
declare the fields the repo can prove.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from widgets import about, runtime

ENGINE = Path(__file__).resolve().parents[4]

_FULL = {"id": "demo", "name": "Demo", "description": "Una demo.", "owner": "Zaelar", "created": "2026-09-02",
         "licence": "SUL-1.0", "connector_families": ["contactos"]}
_BARE = {"id": "bare", "name": "Bare", "description": "Algo suyo.", "origin": "user"}
_INVENTORY = [
    {"id": "google-contacts", "label": "Google Contacts", "family": "contactos", "families": ["contactos"],
     "connected": True},
    {"id": "telegram", "label": "Telegram", "family": "mensajeria", "families": ["mensajeria", "contactos"],
     "connected": False},
    {"id": "spotify", "label": "Spotify", "family": "musica", "families": ["musica"], "connected": True},
]


@pytest.fixture
def catalog(monkeypatch):
    rows = {"demo": dict(_FULL), "bare": dict(_BARE)}
    monkeypatch.setattr(runtime, "get", lambda wid: rows.get(wid))
    from connectors import registry as conn
    monkeypatch.setattr(conn, "descriptors", lambda: [dict(d) for d in _INVENTORY])
    return rows


def test_a_declared_field_is_on_the_page(catalog):
    p = about.about("demo")
    assert p["owner"] == "Zaelar" and p["created"] == "2026-09-02" and p["licence"] == "SUL-1.0"
    assert p["about"]
    assert [c["id"] for c in p["connectors"]] == ["google-contacts", "telegram"], \
        "the page lists what serves the family — through `families` too — and nothing of another family"
    assert p["connectors"][0]["connected"] is True and p["connectors"][1]["connected"] is False


def test_an_undeclared_field_is_absent_not_empty(catalog):
    p = about.about("bare")
    assert set(p) == {"id", "name", "origin", "about"}, p
    assert p["origin"] == "user"


def test_a_malformed_value_is_not_shown(catalog):
    catalog["demo"].update(created="last tuesday", licence="free <b>forever</b>", connector_families="contactos")
    p = about.about("demo")
    assert "created" not in p and "licence" not in p and "connectors" not in p, p


def test_an_unknown_app_has_no_page(catalog):
    assert about.about("nope") is None


def test_a_fork_says_since_when_it_is_his(catalog):
    catalog["demo"]["forked_from"] = {"origin": "builtin", "engine": "1.0", "date": "2026-10-01"}
    assert about.about("demo")["forked"] == "2026-10-01"


_SHIPPED = sorted(p.parent.name for p in (ENGINE / "widgets").glob("*/manifest.json"))
_FAMILY = {"agenda": "agenda", "archivos": "archivos", "contactos": "contactos", "fotos": "fotos",
           "mensajeria": "mensajeria", "musica": "musica", "youtube": "video"}


@pytest.mark.parametrize("wid", _SHIPPED)
def test_every_shipped_app_declares_what_the_repo_can_prove(wid):
    m = json.loads((ENGINE / "widgets" / wid / "manifest.json").read_text(encoding="utf-8"))
    assert m.get("owner") == "Zaelar"
    assert m.get("licence") == "SUL-1.0", "the engine's LICENSE.md covers every shipped widget"
    if wid in _FAMILY:
        assert m.get("connector_families") == [_FAMILY[wid]]
    else:
        assert "connector_families" not in m
    for lang in ("en", "es"):
        ui = json.loads((ENGINE / f"i18n/genesis/{lang}/ui.json").read_text(encoding="utf-8"))
        assert ui.get(f"widgets.{wid}.about"), f"widgets.{wid}.about is missing in {lang}"


def test_the_page_is_served_where_the_window_reads_it(catalog):
    """The window fetches `/widgets/<id>/about` from the widgets router: a route that is defined but not mounted
    there fails EMPTY (every page a 404), so it is read through the router the app mounts."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from widgets import server_api
    app = FastAPI()
    app.include_router(server_api.router)
    c = TestClient(app)
    r = c.get("/widgets/demo/about")
    assert r.status_code == 200 and r.json()["owner"] == "Zaelar"
    assert c.get("/widgets/nope/about").status_code == 404
