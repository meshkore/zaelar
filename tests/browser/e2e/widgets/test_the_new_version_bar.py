"""V2-553 — «hay una versión nueva, pulsa aquí» RENDERED, and the badge that keeps counting.

The operator asked for two surfaces and one rule between them:

    «cuando se actualiza el código […] el frontend tiene que detectarlo y tiene que sacar una barra
     horizontal por encima de todo que diga que hay una nueva versión operativa, pulsa aquí para reiniciar
     el navegador […] obviamente en el caso de que los cambios requieran un reinicio del frontend; si solo
     se ha tocado algo del backend obviamente no hace falta […] y en la barra vertical abajo del todo ver el
     número de versión […] que el número de versión se actualice dinámicamente me parecería perfecto, para
     que el usuario, aunque tenga el navegador abierto tres días, pueda ver cómo ha ido subiendo ese número.»

The rule is the interesting half, and it is the one only a browser can check: a release that moves the
build number but not a single byte of frontend must move the NUMBER and show NO bar. The engine's side of
that decision is unit-tested (`test_the_update_channel_tells_the_ui_from_the_engine.py`); what happens here
is whether the tab acts on it — the bar's visibility, the `--banner-h` seam that shifts the top controls,
the dismissal that lasts exactly one revision, and the reload.

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
  const ver = document.getElementById('hb-upd-ver');
  const vis = el => { if (!el) return false; const r = el.getBoundingClientRect();
                      const cs = getComputedStyle(el);
                      return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden'; };
  const tr = document.querySelector('.tr');
  return {
    barFound: !!bar, barOn: vis(bar),
    barText: bar ? (bar.querySelector('.u-msg') || {}).textContent || '' : '',
    verFound: !!ver, verOn: vis(ver), verText: ver ? ver.textContent.trim() : '',
    verTitle: ver ? (ver.getAttribute('title') || '') : '',
    banner: getComputedStyle(document.documentElement).getPropertyValue('--banner-h').trim(),
    trTop: tr ? Math.round(tr.getBoundingClientRect().top) : null,
    marker: window.__updMarker || null,
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


def test_the_bar_and_the_badge(run):
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
        assert s["barFound"] and s["verFound"], "the update surface did not mount at all"
        assert not s["barOn"], "a fresh load must NEVER offer a reload: nothing is stale yet"
        assert s["verOn"], "the build number is always visible — that is the point of the badge"
        assert s["verText"] == f"v{upd.build()}", f"badge shows {s['verText']!r}, engine says v{upd.build()}"
        assert s["banner"] in ("0px", "0"), f"--banner-h must be 0 with no bar (was {s['banner']!r})"
        assert "update.version_title" not in s["verTitle"] and len(s["verTitle"]) > 8, \
            f"the tooltip is showing a raw i18n key: {s['verTitle']!r}"
        top_clear = s["trTop"]

        # ── A BACKEND-ONLY RELEASE: the number climbs, nobody is interrupted ────────────────────────────
        # This is the operator's rule and the reason the payload carries two fields instead of one.
        _serve(pg, {**live, "build": live["build"] + 41})
        _wake(pg)
        s = pg.evaluate(_STATE)
        assert s["verText"] == f"v{live['build'] + 41}", \
            "the number has to climb live — «aunque tenga el navegador abierto tres días»"
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
        assert s["verOn"], "the badge is not part of the dismissal — it is not a notice"

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


def test_the_number_gets_out_of_the_way_when_the_rail_is_folded(run):
    """The badge lives in the widget rail's column. Folded, that column is a 12 px sliver the operator
    asked to have out of the way, and a number floating over the canvas beside it is exactly the «mierda en
    pantalla» V2-542 removed. Rendered, because the rule is a `:has()` selector — a thing that either works
    in the browser or silently does not."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 800})
        pg.goto(run, wait_until="domcontentloaded")
        pg.evaluate("() => localStorage.setItem('wrail.folded', '1')")
        _boot(pg, run)
        s = pg.evaluate(_STATE)
        assert s["verFound"], "the badge must still be in the DOM — it is hidden by CSS, not unmounted"
        assert not s["verOn"], "with the rail folded the number has to disappear with it"

        pg.evaluate("() => localStorage.setItem('wrail.folded', '0')")
        _boot(pg, run)
        assert pg.evaluate(_STATE)["verOn"], "unfolded, the number is back"
        b.close()
