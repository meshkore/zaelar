"""A widget draws the app shell's OWN icons: one shared file, served to widgets as one exact file (V2-831 T-12).

`frontend/app/lib/icons.js` is the one visual language of the product, and the widgets used to keep copies of it
because nothing served it to them — copies that drift (the music card's play icon and the shell's were already two
different triangles). `widgets/client_files.py` now serves that ONE file at its on-disk path, so the same import
resolves under the engine and under any harness that serves the engine tree. It exposes nothing else: not the
folder, not a sibling, not a traversal.

The render half is RENDERED on three origins: the product's route alone (no static tree at all), the widget harness
(route + static tree) and a plain static server — the three places a card is ever loaded from.
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.waiting import port_listening
from widgets import client_files

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from tests.browser import widget_client

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _route_only() -> TestClient:
    app = FastAPI()
    app.include_router(client_files.router)
    return TestClient(app)


def test_the_icon_set_is_served_as_one_exact_file():
    c = _route_only()
    r = c.get(client_files.SHARED_CLIENT_MODULES[0])
    assert r.status_code == 200, "the shared icon set is not served to widgets"
    assert r.headers["content-type"].startswith("text/javascript") and r.headers["cache-control"] == "no-cache"
    assert r.text == (_ENGINE / "frontend/app/lib/icons.js").read_text(encoding="utf-8")


@pytest.mark.parametrize("path", [
    "/frontend/app/lib/dom.js",                         # a sibling
    "/frontend/app/lib/",                               # the folder
    "/frontend/app/core/store.js",                      # the rest of the shell
    "/frontend/app/lib/%2e%2e/core/store.js",           # an encoded traversal
    "/frontend/app/lib/icons.js/..%2F..%2Fcore%2Fstore.js",
    "/frontend/app/core/palette.css",
])
def test_nothing_else_of_the_shell_is_reachable_through_it(path):
    assert _route_only().get(path).status_code == 404, path


def test_it_is_read_only():
    c = _route_only()
    for m in ("post", "put", "delete"):
        assert getattr(c, m)(client_files.SHARED_CLIENT_MODULES[0]).status_code == 405, m


def test_the_gate_and_the_server_read_the_same_list():
    """What the house gate admits and what the server answers is ONE tuple; a second copy is how they drift."""
    from widgets import validator_js
    assert validator_js.SHARED_CLIENT_MODULES is client_files.SHARED_CLIENT_MODULES
    c = _route_only()
    for url in client_files.SHARED_CLIENT_MODULES:
        assert c.get(url).status_code == 200, url
        assert validator_js._scan_widget_js(f'import * as I from "{url}";') is None, url


# ── RENDERED: the two cards that import it paint its glyphs on every origin a card is loaded from ─────────────

def _product_only():
    """The product's route and nothing else — no static tree to fall back on."""
    import threading
    import time

    import uvicorn
    app = FastAPI()
    app.include_router(client_files.router)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    deadline = time.monotonic() + 15
    while not srv.started and time.monotonic() < deadline:
        time.sleep(0.05)
    return port, srv


@pytest.fixture(scope="module", params=["product-route", "widget-harness", "static-server"])
def origin(request):
    kind = request.param
    if kind == "product-route":
        port, srv = _product_only()
        yield f"http://127.0.0.1:{port}"
        srv.should_exit = True
    elif kind == "widget-harness":
        with widget_client.serve() as port:
            yield f"http://127.0.0.1:{port}"
    else:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                               cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_listening(port)
        yield f"http://127.0.0.1:{port}"
        srv.terminate()


@pytest.fixture(scope="module")
def page(origin):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page()
        pg._hb_origin = origin
        yield pg
        browser.close()


def _render(page, wid, data):
    page.goto(page._hb_origin + client_files.SHARED_CLIENT_MODULES[0])       # any same-origin page
    page.set_content("<div id='w' style='width:760px'></div>")
    return page.evaluate(
        """async ([src, data]) => {
             try {
               const mod = await import(src);
               mod.render(document.getElementById('w'), data,
                          {action: () => {}, top: () => {}, openConnector: () => {}, running: true});
               return null;
             } catch (e) { return String(e); }
           }""",
        [f"{page._hb_origin}/widgets/{wid}/widget.js", data])


def test_the_contacts_plug_is_the_shells_plug(page):
    err = _render(page, "contactos", {"contacts": [], "providers": [], "sync": {}})
    assert err is None, f"the card did not load: {err}"
    plug, shell = page.evaluate("""async u => {
        const t = document.createElement('template'); t.innerHTML = (await import(u)).PLUG_ICON;
        return [document.querySelector('.ctplug svg')?.innerHTML || '', t.content.firstElementChild.innerHTML]; }""",
                                page._hb_origin + client_files.SHARED_CLIENT_MODULES[0])
    assert plug and plug == shell, f"the plug is not the shell's own: {plug!r} vs {shell!r}"


def test_the_music_card_loads_on_the_shells_icons(page):
    err = _render(page, "musica", {})
    assert err is None, f"the card did not load: {err}"
    assert page.evaluate("() => document.querySelectorAll('#w svg').length") > 0, "the card painted no icon"
