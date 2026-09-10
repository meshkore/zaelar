"""Maximizing ANY widget now covers the whole viewport — except the bottom system rail (V2-658 follow-up).

The operator, after seeing his own screenshot of a maximized `archivos` card that still sat under the top
icon cluster (Reset, ⚙, ☾, …): *"cuando... se pone en modo pantalla completa significa que cubras toda la
pantalla menos la barra inferior... todos esos iconitos de arriba... los tienes que cubrir... haz que todos
los widgets cubran toda la pantalla"*. V2-596/V2-600 already built exactly this — full-viewport coverage, a
floating exit button (`.hb-cinexit`) — but reserved it for `fullscreen:"native"` widgets ONLY (video), and
deliberately covers the rail too there (full immersion, unchanged). Every OTHER widget now gets the SAME
full-viewport treatment through a SEPARATE class, `.hb-fullwide`, whose one difference is staying below the
bottom rail's z-index — the operator's own rule: the orb/mic/widget-switcher must stay reachable while a
normal widget fills the screen, only video earns total immersion.

RENDERED, not read: which CSS class wins the class LIST is a source fact; whether the resulting geometry and
stacking actually cover the icon cluster while losing to the rail is a layout fact only a browser settles.
"""
import asyncio
import pathlib
import re

import pytest

DESKTOP = pathlib.Path("frontend/app/widgets/desktop.js")

# Minimal real-shaped chrome: the top icon cluster (`.me`, z-index 9000 in the real styles.css) and the
# bottom rail (`#wrail`, z-index 9002, V2-623) — the two landmarks this fix is about, at their REAL values.
_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;background:#0a1017}
  .me{position:fixed;top:16px;left:18px;z-index:9000;width:200px;height:40px;background:#123}
  #wrail{position:fixed;left:0;right:0;bottom:0;z-index:9002;height:60px;background:#124}
  #desk{position:fixed;top:0;bottom:0;left:0;right:0;transform:translate3d(0,0,0)}
  .hb-win{position:absolute;left:80px;top:100px;width:400px;height:300px;background:#223}
  .hb-win.hb-cinema{position:fixed;top:0!important;left:0!important;width:100vw!important;height:100vh!important;
    max-width:none!important;max-height:none!important;padding:0;background:#000;border:0;border-radius:0}
  .hb-stage:has(.hb-win.hb-cinema){z-index:99900}
  .hb-win.hb-fullwide{position:fixed;top:0!important;left:0!important;width:100vw!important;height:100vh!important;
    max-width:none!important;max-height:none!important;padding:0;background:#fff;border:0;border-radius:0}
  .hb-stage:has(.hb-win.hb-fullwide){z-index:9001}
</style></head><body>
  <div class="me"></div><div id="wrail"></div>
  <div id="desk"><div id="wstage" class="hb-stage"></div></div>
</body></html>"""

_SETUP = """(async () => {
  const D = window.__Desktop;
  const d = Object.create(D.prototype);
  d.stage = document.getElementById("wstage");
  d.wins = new Map();
  d.tile = {w:400, h:340, top:70, pad:14};
  d.grid = 5;
  d._meta = null;                              // catalog "not resolved yet" is the default, real-world state
  d._persist = () => {};
  d._uiAudit = () => {};
  d._bringFront = () => {};
  d._resolve = async (baseId) => {};           // never actually resolves in this harness unless a test sets it
  d.canvas = () => ({x0:0, y0:0, x1:2000, y1:2000});

  window.__mk = (id) => {
    const c = document.createElement("div");
    c.className = "hb-win"; c.dataset.wid = id;
    d.stage.appendChild(c);
    d.wins.set(id, {card:c});
    return c;
  };
  window.__d = d;
  return true;
})()"""


def _module_source() -> str:
    src = DESKTOP.read_text(encoding="utf-8")
    src = re.sub(r'^import \{ t as tr \}.*$', 'const tr = (k) => k;', src, count=1, flags=re.M)
    src = re.sub(r'^import \* as store from .*$', 'const store = { lang: () => "en" };', src, count=1, flags=re.M)
    leftover = re.findall(r'^import .*$', src, flags=re.M)
    assert not leftover, f"_module_source() does not stub: {leftover} — every import needs a stub line above"
    return src + "\nwindow.__Desktop = Desktop;\n"


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright.async_api  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


def _run(script):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 1200, "height": 800})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            await pg.route("http://zaelar.test/", lambda r: asyncio.ensure_future(
                r.fulfill(status=200, content_type="text/html", body=_HTML)))
            await pg.goto("http://zaelar.test/")
            await pg.add_script_tag(content=_module_source(), type="module")
            await pg.wait_for_function("() => !!window.__Desktop")
            await pg.evaluate(_SETUP)
            out = await pg.evaluate(script)
            await b.close()
            return out, errors
    return asyncio.run(go())


def test_a_non_native_widget_maximizes_full_viewport_below_the_rail(playwright_available):
    out, errors = _run("""async () => {
      const c = window.__mk("archivos");
      window.__d.maximize("archivos");
      const cr = c.getBoundingClientRect();
      const stage = document.getElementById("wstage");
      return {
        classes: [...c.classList],
        w: cr.width, h: cr.height, top: cr.top, left: cr.left,
        stageZ: getComputedStyle(stage).zIndex,
        railZ: getComputedStyle(document.getElementById("wrail")).zIndex,
      };
    }""")
    assert not errors, errors
    assert "hb-fullwide" in out["classes"] and "hb-cinema" not in out["classes"], out["classes"]
    assert out["w"] >= 1199 and out["h"] >= 799, f"must cover the full viewport: {out}"
    assert out["top"] == 0 and out["left"] == 0
    assert int(out["stageZ"]) < int(out["railZ"]), (
        f"the fullwide stage must stay BELOW the bottom rail: stage={out['stageZ']} rail={out['railZ']}")


def test_a_native_declared_widget_still_gets_cinema_not_fullwide(playwright_available):
    """The regression guard for video (V2-596/V2-600): a widget that DECLARES `fullscreen:"native"` keeps
    the immersive class that covers the rail too — this fix must not water that down."""
    out, errors = _run("""async () => {
      const c = window.__mk("youtube");
      window.__d._meta = {youtube: {fullscreen: "native"}};
      window.__d.maximize("youtube");
      const stage = document.getElementById("wstage");
      return {classes: [...c.classList], stageZ: getComputedStyle(stage).zIndex,
              railZ: getComputedStyle(document.getElementById("wrail")).zIndex};
    }""")
    assert not errors, errors
    assert "hb-cinema" in out["classes"] and "hb-fullwide" not in out["classes"], out["classes"]
    assert int(out["stageZ"]) > int(out["railZ"]), "video's cinema must still cover the rail (unchanged)"


def test_maximizing_again_restores_and_drops_the_fullwide_class(playwright_available):
    out, errors = _run("""async () => {
      const c = window.__mk("archivos");
      c.style.left = "80px"; c.style.top = "100px"; c.style.width = "400px"; c.style.height = "300px";
      window.__d.maximize("archivos");
      const midClasses = [...c.classList];
      window.__d.maximize("archivos");                 // toggle back
      return {midClasses, afterClasses: [...c.classList],
              left: c.style.left, top: c.style.top, width: c.style.width, height: c.style.height};
    }""")
    assert not errors, errors
    assert "hb-fullwide" in out["midClasses"]
    assert "hb-fullwide" not in out["afterClasses"] and "hb-cinema" not in out["afterClasses"]
    assert out["left"] == "80px" and out["width"] == "400px", (
        f"restoring must bring back the pre-maximize geometry: {out}")


def test_an_unresolved_catalog_defaults_to_fullwide_and_upgrades_to_cinema_once_it_answers(playwright_available):
    """The catalog loads lazily. Before it answers, a maximized card provisionally gets `hb-fullwide` (right
    for 13 of 14 widgets) and is corrected to `hb-cinema` if the widget turns out to be video — never the
    other way, since a maximized-then-restored card must not be "corrected" into a class it no longer wants
    (`if(!card._restore) return;` guards exactly that race)."""
    out, errors = _run("""async () => {
      const c = window.__mk("youtube");
      let resolveIt;
      window.__d._resolve = (baseId) => new Promise(res => { resolveIt = res; });
      window.__d.maximize("youtube");
      const beforeResolve = [...c.classList];
      window.__d._meta = {youtube: {fullscreen: "native"}};
      resolveIt();
      await new Promise(r => setTimeout(r, 0));
      return {beforeResolve, afterResolve: [...c.classList]};
    }""")
    assert not errors, errors
    assert "hb-fullwide" in out["beforeResolve"], out["beforeResolve"]
    assert "hb-cinema" in out["afterResolve"] and "hb-fullwide" not in out["afterResolve"], out["afterResolve"]
