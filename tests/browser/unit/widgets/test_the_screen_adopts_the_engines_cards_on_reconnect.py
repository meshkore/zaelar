"""After a reconnect the screen adopts the engine's list of cards (V2-825 F5, refactor2710-04 T-04).

He saw two `documento` cards while the canvas report listed one: a card in the DOM that the desktop's own registry
(`wins`) no longer owned — the report is built from `wins`, so the engine could not name it, close it or answer for
it. `Desktop.reconcile()` runs on every reconnect of the event stream: an orphan goes, a card the engine does not list
closes, a card it lists that is not on screen opens beside without focus, and the drift is reported so the
timeline says how many cards were off (`widget`/`reconcile`).
"""
from __future__ import annotations

import json

import pytest

from tests.browser import widget_client

_PAGE = "<!doctype html><html><body><div id='stage'></div><div id='activity'></div></body></html>"

_DRIVE = """async () => {
  const {Desktop} = await import('/frontend/app/widgets/desktop.js');
  const stage = document.getElementById('stage');
  const d = new Desktop(stage);
  const card = (id) => { const c = document.createElement('div'); c.className = 'hb-win'; c.dataset.wid = id;
                         stage.appendChild(c); return c; };
  d.wins.set('documento', {card: card('documento'), id: 'documento'});   // the card the engine lists
  card('documento');                                                      // the ghost: in the DOM, not in wins
  d.wins.set('agenda', {card: card('agenda'), id: 'agenda'});             // on screen, not in the engine's list
  const closed = [], shown = [];
  d.close = (id, o) => { closed.push([id, o.by]); };
  d.show = async (id, o) => { shown.push([id, o.background, o.by]); };
  const got = await d.reconcile();
  return {got, closed, shown, documentos: stage.querySelectorAll('.hb-win[data-wid="documento"]').length};
}"""


@pytest.fixture(scope="module")
def reconciled():
    from playwright.sync_api import sync_playwright
    reported = []

    def _layout(route):
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"items": [{"id": "documento"}, {"id": "markets"}], "live": []}))

    def _report(route):
        reported.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json", body='{"ok": true}')

    with widget_client.serve() as port, sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page()
        pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
        pg.route("**/api/canvas/layout*", _layout)          # the last route registered wins
        pg.route("**/api/canvas/reconcile", _report)
        pg.route(f"http://127.0.0.1:{port}/", lambda r: r.fulfill(status=200, content_type="text/html", body=_PAGE))
        pg.goto(f"http://127.0.0.1:{port}/")
        out = pg.evaluate(_DRIVE)
        pg.wait_for_timeout(200)
        b.close()
    out["reported"] = reported
    return out


def test_the_orphan_the_engine_cannot_name_goes_and_one_documento_is_left(reconciled):
    assert reconciled["documentos"] == 1, "a ghost card stayed on screen beside the one the engine lists"
    assert reconciled["got"]["orphans"] == ["documento"]


def test_the_screen_takes_the_engines_list_not_the_reverse(reconciled):
    assert reconciled["closed"] == [["agenda", "restore"]], "a card the engine does not list must close"
    assert reconciled["shown"] == [["markets", True, "restore"]], "a card it lists opens beside, without focus"


def test_the_drift_is_reported_for_the_timeline(reconciled):
    assert reconciled["reported"] == [{"orphans": ["documento"], "extra": ["agenda"], "missing": ["markets"]}]


def test_the_engine_records_the_reconcile_as_a_widget_event(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from server import canvas_api
    seen = []
    monkeypatch.setattr(canvas_api, "emit", lambda kind, label, text="", extra=None, **k: seen.append((kind, label, extra)))
    app = FastAPI()
    app.include_router(canvas_api.router)
    TestClient(app).post("/api/canvas/reconcile", json={"orphans": ["documento"], "extra": [], "missing": ["markets"]})
    assert seen == [("widget", "reconcile", {"orphans": ["documento"], "extra": [], "missing": ["markets"],
                                             "src": "client:restore"})]
