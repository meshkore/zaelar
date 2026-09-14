"""V2-553 — «hay una versión nueva, pulsa aquí» RENDERED. V2-666 moved the always-on version badge off the
canvas and into Settings, so this file's original two-surface premise («la barra vertical abajo del todo ver
el número de versión») changed shape; what the operator now asks is stated in his own words below.

    «cuando se actualiza el código […] el frontend tiene que detectarlo y tiene que sacar una barra
     horizontal por encima de todo que diga que hay una nueva versión operativa, pulsa aquí para reiniciar
     el navegador […] obviamente en el caso de que los cambios requieran un reinicio del frontend; si solo
     se ha tocado algo del backend obviamente no hace falta.» (V2-553)

    «Lo de la versión […] quítalo de la escena. Puedes meter la versión dentro del apartado de
     configuración, que haya que abrir el apartado de configuración para ver la versión.» (V2-666, 2026-09-11)

The rule for the BAR is the interesting half, and it is the one only a browser can check: a release that
moves the build number but not a single byte of frontend must move the NUMBER (now inside Settings) and show
NO bar. The engine's side of that decision is unit-tested
(`test_the_update_channel_tells_the_ui_from_the_engine.py`); what happens here is whether the tab acts on it
— the bar's visibility, the `--banner-h` seam that shifts the top controls, the dismissal that lasts exactly
one revision, and the reload — plus, separately, that the version number is genuinely gone from the bare
canvas and genuinely reachable from Settings.

The new versions are simulated by intercepting `/api/update`, so the test drives the REAL client code down
the real path: a synthetic `visibilitychange` is what wakes the watcher, exactly as returning to a tab does.
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
from update.api import router as update_router
app = FastAPI(); app.include_router(pages.router); app.include_router(i18n_api.router)
app.include_router(update_router)
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

_STATE = """() => {
  const bar = document.getElementById('hb-upd-bar');
  const vis = el => { if (!el) return false; const r = el.getBoundingClientRect();
                      const cs = getComputedStyle(el);
                      return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden'; };
  const tr = document.querySelector('.tr');
  return {
    barFound: !!bar, barOn: vis(bar),
    barText: bar ? (bar.querySelector('.u-msg') || {}).textContent || '' : '',
    banner: getComputedStyle(document.documentElement).getPropertyValue('--banner-h').trim(),
    trTop: tr ? Math.round(tr.getBoundingClientRect().top) : null,
    marker: window.__updMarker || null,
  };
}"""

# V2-666 — the version number's own state, read wherever it now lives: nowhere on the bare canvas, and
# inside the Settings header once opened.
_VER_STATE = """() => {
  const ver = document.querySelector('.cf-ver');
  const vis = el => { if (!el) return false; const r = el.getBoundingClientRect();
                      const cs = getComputedStyle(el);
                      return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden'; };
  return {
    onCanvasById: !!document.getElementById('hb-upd-ver'),   // the retired always-on badge — must never exist
    inSettings: !!ver, settingsOn: vis(ver),
    settingsText: ver ? ver.textContent.trim() : '',
    settingsTitle: ver ? (ver.getAttribute('title') || '') : '',
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


def _serve(pg, payload: dict):
    """Answer /api/update with `payload` from now on. Everything else goes to the real server."""
    pg.unroute("**/api/update")
    pg.route("**/api/update",
             lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(payload)))


def _wake(pg):
    """What returning to a backgrounded tab does. The real listener, the real check, no test-only hook."""
    pg.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    pg.wait_for_timeout(700)


def test_the_bar(run):
    import update as upd
    from playwright.sync_api import sync_playwright

    live = {"build": upd.build(), "version": upd.VERSION if hasattr(upd, "VERSION") else "",
            "sha": "test", "short": "test", "ui_rev": upd.ui_rev(),
            "started_ms": 0, "deploy": "local"}
    # The digest the preview server really serves — taken from the module, not invented, so the baseline
    # this tab adopts is the one the engine would have given it.
    live["ui_rev"] = upd.ui_rev()

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 800})
        _boot(pg, run)

        # ── a tab running exactly what the engine serves ────────────────────────────────────────────────
        s = pg.evaluate(_STATE)
        assert s["barFound"], "the update surface did not mount at all"
        assert not s["barOn"], "a fresh load must NEVER offer a reload: nothing is stale yet"
        assert s["banner"] in ("0px", "0"), f"--banner-h must be 0 with no bar (was {s['banner']!r})"
        top_clear = s["trTop"]

        # ── A BACKEND-ONLY RELEASE: nobody is interrupted ───────────────────────────────────────────────
        # This is the operator's rule and the reason the payload carries two fields instead of one. The
        # number itself now lives in Settings (V2-666) and is checked separately below.
        _serve(pg, {**live, "build": live["build"] + 41})
        _wake(pg)
        s = pg.evaluate(_STATE)
        assert not s["barOn"], "the frontend did not change: offering a reload here is the nag he asked to avoid"
        assert s["trTop"] == top_clear, "nothing may move for a backend-only release"

        # ── A REAL FRONTEND RELEASE ─────────────────────────────────────────────────────────────────────
        _serve(pg, {**live, "build": live["build"] + 42, "ui_rev": "0000ffff0000ffff"})
        _wake(pg)
        s = pg.evaluate(_STATE)
        assert s["barOn"], "the served frontend differs from the one running and no bar appeared"
        assert s["barText"] and s["barText"] != "update.available", \
            f"the bar is rendering a raw i18n key: {s['barText']!r}"
        assert s["banner"] == "36px", f"--banner-h must carry the bar's height (was {s['banner']!r})"
        assert s["trTop"] > top_clear, \
            "the top-right toolbar has to slide down instead of being covered by the bar"

        # ── ✕ dismisses THIS revision, and gives the top controls back ─────────────────────────────────
        pg.click("#hb-upd-bar .u-x")
        pg.wait_for_timeout(400)
        s = pg.evaluate(_STATE)
        assert not s["barOn"], "✕ must put the bar away"
        assert s["banner"] in ("0px", "0"), "dismissing has to release --banner-h, or the toolbar stays pushed down"

        _wake(pg)
        s = pg.evaluate(_STATE)
        assert not s["barOn"], "a dismissed revision must stay dismissed while it is the one being served"

        # ── …but only THAT revision. The next one comes back ────────────────────────────────────────────
        _serve(pg, {**live, "build": live["build"] + 43, "ui_rev": "1111aaaa1111aaaa"})
        _wake(pg)
        assert pg.evaluate(_STATE)["barOn"], \
            "«ahora no» cannot mean «never again»: a NEW version has to ask again"

        # ── clicking the bar reloads the tab ────────────────────────────────────────────────────────────
        # The whole strip is the target, not just the button: he described it as «pulsa aquí».
        pg.evaluate("() => { window.__updMarker = 'before'; }")
        assert pg.evaluate(_STATE)["marker"] == "before"
        pg.click("#hb-upd-bar .u-msg")
        pg.wait_for_load_state("domcontentloaded")
        pg.wait_for_timeout(1800)
        assert pg.evaluate(_STATE)["marker"] is None, \
            "clicking the bar did not reload the page — the one thing the bar exists to do"

        b.close()


def test_the_version_left_the_scene_and_lives_in_settings(run):
    """V2-666, the operator: «Lo de la versión 11 quítalo de la escena […] puedes meter la versión dentro
    del apartado de configuración, que haya que abrir el apartado de configuración para ver la versión.»
    Two claims, both false until this shipped: (1) nothing on the bare canvas names the build number any
    more — not the retired `#hb-upd-ver` id, not any visible text; (2) opening ⚙ Settings shows it, live,
    reading the SAME `update/watch.js` signal the old badge read."""
    import update as upd
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 800})
        _boot(pg, run)

        # ── the bare canvas: no version anywhere VISIBLE ────────────────────────────────────────────────
        # (Settings' own overlay, `.cf-ver` included, mounts hidden at boot like every other system overlay
        # — the claim is about what a person can SEE, not about the node existing off-screen in the DOM.)
        gone = pg.evaluate(_VER_STATE)
        assert not gone["onCanvasById"], "the retired #hb-upd-ver badge is back on the canvas"
        assert not gone["settingsOn"], "the version must not be visible before Settings is opened"

        # ── open ⚙ Settings: the version is right there, live ───────────────────────────────────────────
        pg.click("#cfgBtn")
        pg.wait_for_timeout(700)
        s = pg.evaluate(_VER_STATE)
        assert not s["onCanvasById"], "opening Settings must not resurrect the old badge id"
        assert s["inSettings"] and s["settingsOn"], f"the version never rendered in Settings: {s}"
        assert s["settingsText"] == f"v{upd.build()}", \
            f"Settings shows {s['settingsText']!r}, engine says v{upd.build()}"
        assert "update.version_title" not in s["settingsTitle"] and len(s["settingsTitle"]) > 8, \
            f"the tooltip is showing a raw i18n key: {s['settingsTitle']!r}"
        b.close()
