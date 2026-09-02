"""V2-550 — the chat wall comes back open, on its tab, where it was left.

The operator: «cuando refresco el navegador, más o menos respeta los widgets abiertos con su contenido y los
deja en su posición. Pero el widget del Chat Wall, que es más o menos un widget de sistema, si estaba abierto,
no lo deja donde estaba.»

His report was precise in a way worth keeping: the POSITION was never the part that was lost. The wall has
persisted its floating rect and its docked side since V2-062. What it never persisted is being OPEN —
`store.chatOpen` is a signal born `false` — so a reload always came back closed, and reopening it then restored
the geometry correctly. That is exactly what «it does not stay where it was» looks like from outside.

Only a browser can answer this: it is about what survives a real reload, through real `localStorage`, in a
panel that decides its own geometry at construction time.
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

_STATE = """() => {
  const w = document.querySelector('.chatwall, #chatwall, .cw, .hb-chatwall');
  const vis = el => { if (!el) return false; const r = el.getBoundingClientRect();
                      const cs = getComputedStyle(el);
                      return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden'; };
  let saved = null; try { saved = JSON.parse(localStorage.getItem('hb_chat_open') || 'null'); } catch (_) {}
  const r = w ? w.getBoundingClientRect() : null;
  return {
    found: !!w,
    open: vis(w),
    rect: r ? {left: Math.round(r.left), top: Math.round(r.top),
               w: Math.round(r.width), h: Math.round(r.height)} : null,
    saved: saved,
    tab: (document.querySelector('.cw-tab.on, .cw-tabs .on') || {}).textContent || '',
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


@pytest.fixture(scope="module")
def measured(run):
    """One browser, one profile: open the wall, move it, reload, and look — the operator's own sequence."""
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        _boot(pg, run)
        out["fresh"] = pg.evaluate(_STATE)                    # a first-ever visit: closed

        # Open it the way the product does, through the store the components share.
        pg.evaluate("""async () => {
          const s = await import('/static/app/core/store.js?v=2');
          s.setChatTab('procesos'); s.setChatOpen(true);
        }""")
        pg.wait_for_timeout(500)
        # Move it somewhere unmistakable and let the panel save that rect.
        pg.evaluate("""async () => {
          const w = document.querySelector('.chatwall, #chatwall, .cw, .hb-chatwall');
          if (!w) return;
          w.style.left = '640px'; w.style.top = '120px'; w.style.width = '380px'; w.style.height = '420px';
          localStorage.setItem('hb_chat_float', JSON.stringify({left:640, top:120, w:380, h:420}));
        }""")
        pg.wait_for_timeout(300)
        out["before"] = pg.evaluate(_STATE)

        _boot(pg, run)                                        # THE RELOAD
        pg.wait_for_timeout(600)
        out["after"] = pg.evaluate(_STATE)
        out["errors"] = errors
        b.close()
    return out


def test_the_panel_is_found_and_the_page_has_no_errors(measured):
    assert measured["before"]["found"], "the chat wall never mounted — the rest measures nothing"
    assert measured["errors"] == [], measured["errors"]


def test_a_first_visit_still_starts_with_it_CLOSED(measured):
    """Remembering must not mean defaulting to open: someone who has never opened it should not meet it."""
    assert not measured["fresh"]["open"], json.dumps(measured["fresh"])


def test_it_comes_back_OPEN_after_a_reload(measured):
    """THE defect. It used to come back closed every single time."""
    assert measured["before"]["open"], "it did not open in the first place"
    assert measured["after"]["open"], \
        "the chat wall came back CLOSED after a reload — this is the operator's report, verbatim"


def test_it_comes_back_IN_THE_SAME_PLACE(measured):
    """The half he described as lost. The geometry always persisted; what makes it *look* preserved is coming
    back open ON it, so both halves are asserted together or neither means anything."""
    a, b_ = measured["before"]["rect"], measured["after"]["rect"]
    assert a and b_, (a, b_)
    for k in ("left", "top", "w", "h"):
        assert abs(a[k] - b_[k]) <= 2, f"{k}: {a[k]} → {b_[k]} ({a} → {b_})"


def test_it_comes_back_ON_THE_SAME_TAB(measured):
    """Finding «Chat» after leaving it on «Procesos» is the same loss one level down."""
    saved = measured["after"]["saved"] or {}
    assert saved.get("tab") == "procesos", saved
