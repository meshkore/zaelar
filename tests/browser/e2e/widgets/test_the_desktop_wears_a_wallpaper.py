"""V2-641 — the desktop background is a SPOKEN property: a photo the voice can put behind everything.

The operator's spec (2026-09-09): «quiero poder poner una imagen de fondo… igual que podemos con la voz
colocar widgets o pasar el orbe a la barra». What only a browser can check: that the URL actually PAINTS
(class + custom property + computed background on the rendered .canvas), that the scrim keeps the desk
legible over any photo, that the server's copy wins at boot (a fresh browser must show the account's
wallpaper), and that clearing returns the desk to its gradient ground with nothing left behind.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

import pytest

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

PREVIEW = '''
import sys; sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from server import pages, i18n_api
app = FastAPI(); app.include_router(pages.router); app.include_router(i18n_api.router)
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

WALL_URL = "https://images.example.com/gran-canyon-2900x1440.jpg"

_STATE = """() => {
  const canvas = document.querySelector('.canvas');
  const cs = canvas ? getComputedStyle(canvas) : null;
  const after = canvas ? getComputedStyle(canvas, '::after') : null;
  let stored = null;
  try { stored = localStorage.getItem('hb_wallpaper'); } catch (_) {}
  return {
    cls: document.body.classList.contains('hb-wallpaper'),
    varSet: getComputedStyle(document.documentElement).getPropertyValue('--desk-wallpaper').trim(),
    painted: cs ? cs.backgroundImage : '',
    scrimOpacity: after ? parseFloat(after.opacity || '0') : 0,
    stored: stored,
  };
}"""


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def run():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-c", PREVIEW % (ENGINE, os.path.join(ENGINE, "frontend"), port)],
                            cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); break
        except OSError:
            time.sleep(0.5)
    else:  # pragma: no cover
        proc.terminate(); pytest.skip("preview server never came up")
    time.sleep(1.0)
    yield f"http://127.0.0.1:{port}/"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover
        proc.kill()


def _boot(pg, url):
    pg.goto(url, wait_until="domcontentloaded")
    pg.wait_for_timeout(2200)
    pg.evaluate("() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil').forEach(e=>e.remove())")
    pg.wait_for_timeout(300)


@pytest.fixture(scope="module")
def measured(run):
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1280, "height": 800})

        # The account's copy WINS at boot: a fresh browser (empty localStorage) must come up wearing the
        # server's wallpaper — that is the reconcile in theme.js, measured end to end via a mocked
        # /api/settings (the preview harness carries no live settings route).
        settings = {"theme": {}, "wallpaper": {"url": WALL_URL, "title": "Gran Cañón"}}
        pg = ctx.new_page()
        pg.route("**/api/settings", lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(settings)))
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        _boot(pg, run)
        pg.wait_for_timeout(600)                       # the reconcile fetch lands after first paint
        out["boot_from_server"] = pg.evaluate(_STATE)

        # Live application (what the SSE push does after a voice order) — and the clear.
        pg.evaluate("() => import('/static/app/services/theme.js?v=2').then(m => m.setWallpaper("
                    "{url: 'https://images.example.com/other.jpg', title: 'Otra'}, {persist: false}))")
        pg.wait_for_timeout(300)
        out["after_swap"] = pg.evaluate(_STATE)
        pg.evaluate("() => import('/static/app/services/theme.js?v=2').then(m => m.setWallpaper(null, {persist: false}))")
        pg.wait_for_timeout(300)
        out["after_clear"] = pg.evaluate(_STATE)
        out["errors"] = list(errors)
        ctx.close(); b.close()
    return out


def test_the_servers_wallpaper_paints_a_fresh_browser(measured):
    st = measured["boot_from_server"]
    assert st["cls"], "body must carry the hb-wallpaper class after the boot reconcile"
    assert WALL_URL in st["varSet"], f"--desk-wallpaper must hold the account's url: {st['varSet']!r}"
    assert WALL_URL in st["painted"], f"the RENDERED .canvas must actually paint it: {st['painted'][:120]!r}"
    assert not measured["errors"], f"no page errors during the whole ride: {measured['errors']}"


def test_the_scrim_keeps_the_desk_legible_over_any_photo(measured):
    st = measured["boot_from_server"]
    assert 0.1 < st["scrimOpacity"] < 0.9, \
        f"the ::after scrim must dim the photo (got opacity {st['scrimOpacity']})"


def test_a_live_swap_repaints_without_reload(measured):
    st = measured["after_swap"]
    assert "other.jpg" in st["painted"], "the SSE-path application must repaint the canvas in place"
    assert "other.jpg" in (st["stored"] or ""), "and localStorage keeps it for the next instant boot"


def test_clearing_returns_the_gradient_ground(measured):
    st = measured["after_clear"]
    assert not st["cls"] and st["varSet"] == "", "no class, no property left behind"
    assert "example.com" not in st["painted"], f"the photo must be GONE from the render: {st['painted'][:120]!r}"
