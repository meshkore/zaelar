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


# ── V2-608: docking the wall must ANNOUNCE that the canvas changed shape ────────────────────────────────────
@pytest.fixture(scope="module")
def docked(run):
    """The operator's gesture: the chat wall takes a full-height column on the left.

    Measured on the REAL page, with the real ChatWall, because the half under test is one line inside a closure
    (`setReserve`) that nothing exports. The companion test
    (`test_the_canvas_refits_when_the_chat_takes_a_column.py`) drives the desktop by dispatching that event; if
    only that one existed, deleting the dispatch would leave both suites green and the operator's screen broken.
    """
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        # Installed BEFORE any script on the page, so the wall's construction-time dock is not missed.
        ctx.add_init_script("""
          window.__canvasEvents = [];
          document.addEventListener("hb:canvas-resized", e => {
            window.__canvasEvents.push((e.detail && e.detail.side) || null);
          });
          try {
            localStorage.setItem("hb_chat_dock", JSON.stringify({side:"left", w:420}));
            localStorage.setItem("hb_chat_open", JSON.stringify({open:true, tab:"chat"}));
          } catch (_) {}
        """)
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        _boot(pg, run)
        pg.wait_for_timeout(800)
        out["events"] = pg.evaluate("() => window.__canvasEvents")
        out["dock_l"] = pg.evaluate(
            "() => getComputedStyle(document.documentElement).getPropertyValue('--chatdock-l').trim()")
        out["wall"] = pg.evaluate("""() => {
          const w = document.querySelector('#chatwall, .chatwall');
          if (!w) return null;
          const r = w.getBoundingClientRect();
          return {left: Math.round(r.left), right: Math.round(r.right), w: Math.round(r.width)};
        }""")
        # V2-608 — the dock classes are set imperatively; the wall's `class` is a REACTIVE binding that rebuilds
        # the whole className on any tab/open change. Switching tabs is the cheapest way to make it re-run.
        pg.evaluate("""async () => { const s = await import('/static/app/core/store.js?v=2'); s.setChatTab('procesos'); }""")
        pg.wait_for_timeout(400)
        out["after_tab"] = pg.evaluate("""() => {
          const w = document.querySelector('#chatwall, .chatwall');
          const r = w.getBoundingClientRect();
          return {cls: [...w.classList].join(' '), h: Math.round(r.height), w: Math.round(r.width),
                  dockL: getComputedStyle(document.documentElement).getPropertyValue('--chatdock-l').trim()};
        }""")
        out["undock_visible"] = pg.evaluate("""() => {
          const u = document.querySelector('#chatwall .cw-undock');
          if (!u) return null;
          const r = u.getBoundingClientRect();
          return {shown: !u.classList.contains('hidden') && r.width > 0, top: Math.round(r.top)};
        }""")
        # With the update banner up, a full-height column used to slide its own header underneath it.
        pg.evaluate("() => document.documentElement.style.setProperty('--banner-h', '44px')")
        pg.wait_for_timeout(250)
        out["with_banner"] = pg.evaluate("""() => {
          const w = document.querySelector('#chatwall');
          const h = document.querySelector('#chatwall .cw-head');
          const u = document.querySelector('#chatwall .cw-undock');
          const x = document.querySelector('#chatwall .cw-x');
          const vis = el => { const r = el.getBoundingClientRect();
            return r.top >= 44 && document.elementFromPoint(r.left + r.width/2, r.top + r.height/2) !== null
                   && el.contains(document.elementFromPoint(r.left + r.width/2, r.top + r.height/2)); };
          return {wallTop: Math.round(w.getBoundingClientRect().top),
                  headTop: Math.round(h.getBoundingClientRect().top),
                  undockReachable: vis(u), closeReachable: vis(x)};
        }""")
        # And the way back: press undock and the column becomes the floating chat panel again.
        pg.evaluate("() => document.querySelector('#chatwall .cw-undock').click()")
        pg.wait_for_timeout(400)
        out["after_undock"] = pg.evaluate("""() => {
          const w = document.querySelector('#chatwall');
          const r = w.getBoundingClientRect();
          return {cls: [...w.classList].join(' '), w: Math.round(r.width), h: Math.round(r.height),
                  dockL: getComputedStyle(document.documentElement).getPropertyValue('--chatdock-l').trim(),
                  deskLeft: Math.round(document.getElementById('desk').getBoundingClientRect().left)};
        }""")
        out["errors"] = errors
        b.close()
    return out


def test_a_docked_wall_COMES_BACK_docked(docked):
    """V2-608. `hb_chat_dock` was written on every dock and never read back on restore, so `floatGeo` — which
    `applyDock` does not clear — always won and the wall returned FLOATING. Measured on the real page before the
    fix: left:18 w:320 `docked:false`, with `hb_chat_dock` still holding `{side:"left",w:420}`. V2-550 fixed «it
    does not come back where it was» for the floating wall; this is the same report for the docked one, and
    docked is the shape the operator actually uses."""
    assert docked["wall"], "the chat wall never mounted"
    assert docked["wall"]["left"] == 0 and docked["wall"]["w"] == 420, docked["wall"]


def test_the_reserved_strip_MATCHES_the_column_it_reserves(docked):
    """They are two numbers for one edge, and they disagreed. `setReserve` measured `offsetWidth`, which is 0
    while the wall is still unlaid-out — the restore path exactly — so it reserved the 340px default for a 420px
    column and left an 80px band of desk hidden underneath the chat."""
    assert docked["dock_l"] == f"{docked['wall']['w']}px", \
        f"strip {docked['dock_l']} vs column {docked['wall']['w']}px"


def test_docking_ANNOUNCES_the_new_canvas(docked):
    """THE missing link. `#desk` follows `--chatdock-l` in CSS, but the widget cards live on `.hb-stage`
    (`inset:0`) in viewport coordinates — so unless somebody says the canvas moved, they simply stay put and the
    desk shrinks underneath them. That is the operator's screenshot: chat docked left, cards untouched, the one
    on the right cut off by the window edge with no way to reach it."""
    assert docked["events"], "docking the chat wall fired no hb:canvas-resized at all"
    assert "left" in docked["events"], docked["events"]
    assert docked["errors"] == [], docked["errors"]


def test_a_TAB_CHANGE_does_not_secretly_undock_the_wall(docked):
    """The defect behind the operator's second screenshot (V2-608). `class` is a reactive binding —
    `"chatwall tab-" + tab + (open ? " open" : "")` — that rewrites the WHOLE className, while `docked`/
    `dock-left` are set imperatively by `applyDock`. So any tab or open change wiped them, leaving `dockSide`
    still set: the wall rendered as a floating panel at left:0 (top:232 h:480) AND still reserved a full 420px
    column, so the entire desk was pushed right by a column that was no longer there.

    Reproduced headless before the fix, verbatim: classes `chatwall tab-chat open`, `--chatdock-l: 420px`."""
    a = docked["after_tab"]
    assert "docked" in a["cls"] and "dock-left" in a["cls"], f"the tab change undocked it: {a['cls']}"
    assert a["h"] >= 700, f"a docked wall is a FULL-HEIGHT column, not a floating panel: {a}"
    assert a["dockL"] == f"{a['w']}px", f"strip and column disagree after the rebuild: {a}"


def test_a_docked_column_ALWAYS_offers_a_way_out(docked):
    """Operator, 2026-09-07: «no veo forma de cerrarlo… esa barra tiene que poder moverse y tiene que haber un
    icono para minimizarla».

    It matters because the wall can be opened by the AGENT — a proactive push showing the cluster list is what
    happened to him — so it can arrive docked without him having docked it. Dragging the header back out is not
    discoverable, and the × beside it CLOSES the panel instead of giving him the chat back."""
    u = docked["undock_visible"]
    assert u and u["shown"], "a docked column with no visible way out"


def test_the_update_banner_does_not_bury_the_columns_own_header(docked):
    """`--banner-h` was honoured by `.me` and `.tr` and by nothing else, so a full-height column ran from y=0 and
    put its tabs AND both its buttons underneath the banner. That is why he could not close it."""
    b = docked["with_banner"]
    assert b["wallTop"] >= 44, f"the column still starts under the banner: {b}"
    assert b["headTop"] >= 44, b
    assert b["undockReachable"], f"the undock button is not clickable: {b}"
    assert b["closeReachable"], f"the close button is not clickable: {b}"


def test_undocking_gives_him_the_CHAT_WIDGET_back(docked):
    """«Se minimiza la barra y vuelve a aparecer el widget del chat.» Not closed — floating, with its content."""
    a = docked["after_undock"]
    assert "docked" not in a["cls"] and "open" in a["cls"], a
    assert a["h"] < 700, f"still a full-height column: {a}"
    assert a["dockL"] == "0px" and a["deskLeft"] == 0, f"the desk did not get its space back: {a}"
