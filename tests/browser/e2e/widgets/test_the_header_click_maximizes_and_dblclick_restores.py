"""A DOUBLE-click on a card's header toggles fullscreen, BOTH ways (V2-658 follow-up).

The operator's own words, and his own correction the moment he tried the first cut live: *"cuidado, he dicho
que se hacía un widget fullscreen cuando se hace doble clic... no solo un clic, ahora mismo lo acabo de probar
y me pide solo un clic y de golpe ya se maximiza"*. A single click/tap on the header must stay a no-op — it is
also the resting state of the DRAG gesture, and a hand merely repositioning the card must never blow it up to
fullscreen by accident. Only an explicit double-click, the OS title-bar convention, toggles it — and it toggles
BOTH ways, because `maximize()` already IS a toggle (`card._restore` truthy ⇒ restore, else maximize;
V2-600/V2-609 already persist the pre-maximize geometry) — this only wires the GESTURE onto `.hb-head`, the
same element `_dragHandle` already treats as an OS title bar (V2-608 F6).

RENDERED, not read: whether a tap is told apart from a drag, and a click on the header's OWN buttons is told
apart from a tap on empty header space, are layout/event facts no source read can settle.
"""
import asyncio
import pathlib
import re

import pytest

DESKTOP = pathlib.Path("frontend/app/widgets/desktop.js")

_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;background:#0a1017}
  .hb-win{position:absolute;left:80px;top:100px;width:400px;height:300px;background:#223}
  .hb-head{position:absolute;top:6px;left:12px;right:70px;height:24px;cursor:grab}
  .hb-name,.hb-cfg{pointer-events:auto}
</style></head><body>
  <div id="desk"><div id="wstage"></div></div>
</body></html>"""

_SETUP = """(async () => {
  const D = window.__Desktop;
  const d = Object.create(D.prototype);
  d.stage = document.getElementById("wstage");
  d.wins = new Map();
  d._persist = () => {};
  d._uiAudit = () => {};
  d._bringFront = () => {};
  d.canvas = () => ({x0:0, y0:0, x1:2000, y1:2000});
  d.deskBox = () => ({left:0, top:0});
  d._snap = (n) => n;
  window.__calls = [];
  d.maximize = (id) => { window.__calls.push(id); };

  window.__mk = (id) => {
    const c = document.createElement("div");
    c.className = "hb-win"; c.dataset.wid = id;
    const head = document.createElement("div");
    head.className = "hb-head";
    const nameBtn = document.createElement("button");
    nameBtn.className = "hb-name"; nameBtn.textContent = id;
    window.__nameClicks = window.__nameClicks || 0;
    nameBtn.onclick = () => { window.__nameClicks++; };
    head.appendChild(nameBtn);
    c.appendChild(head);
    d.stage.appendChild(c);
    d.wins.set(id, {card:c});
    d._wireDrag(c);
    return {card:c, head, nameBtn};
  };
  window.__d = d;
  return true;
})()"""


def _module_source() -> str:
    """desktop.js with its top-of-file imports stubbed — this route-mocked page has no static server, so a
    real ../core import would fail the whole script tag in silence (the V2-613 sweep's own lesson)."""
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
            pg = await b.new_page(viewport={"width": 1000, "height": 800})
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


# A synthetic tap: pointerdown then pointerup at the SAME point, dispatched on the given element.
_TAP = """(el) => {
  const opts = {bubbles:true, clientX:200, clientY:110, pointerId:1};
  el.dispatchEvent(new PointerEvent("pointerdown", opts));
  window.dispatchEvent(new PointerEvent("pointerup", opts));
}"""

_DRAG = """(el) => {
  el.dispatchEvent(new PointerEvent("pointerdown", {bubbles:true, clientX:200, clientY:110, pointerId:1}));
  window.dispatchEvent(new PointerEvent("pointermove", {bubbles:true, clientX:260, clientY:150, pointerId:1}));
  window.dispatchEvent(new PointerEvent("pointerup", {bubbles:true, clientX:260, clientY:150, pointerId:1}));
}"""

_DBLCLICK = """(el) => {
  el.dispatchEvent(new MouseEvent("dblclick", {bubbles:true, clientX:200, clientY:110}));
}"""


def test_a_single_tap_on_the_header_never_maximizes(playwright_available):
    """The corrected rule: a lone click/tap on the header — maximized or not — is a no-op. It is also the
    resting state of a drag gesture, so treating it as "maximize" would fire on every drag's mousedown."""
    out, errors = _run(f"""async () => {{
      const {{head}} = window.__mk("archivos");
      ({_TAP})(head);
      return {{calls: window.__calls.slice()}};
    }}""")
    assert not errors, errors
    assert out["calls"] == [], f"a single tap must never maximize: {out}"


def test_a_double_click_on_a_normal_header_maximizes_it(playwright_available):
    out, errors = _run(f"""async () => {{
      const {{head}} = window.__mk("archivos");
      ({_DBLCLICK})(head);
      return {{calls: window.__calls.slice()}};
    }}""")
    assert not errors, errors
    assert out["calls"] == ["archivos"], out


def test_a_double_click_on_a_maximized_header_restores_it(playwright_available):
    """Same gesture, opposite direction — `maximize()` is already a toggle on `card._restore`, so wiring the
    SAME dblclick listener to it is what makes double-click undo itself."""
    out, errors = _run(f"""async () => {{
      const {{card, head}} = window.__mk("archivos");
      card._restore = {{left:"10px", top:"10px", w:"400px", h:"300px"}};   // simulate already maximized
      ({_DBLCLICK})(head);
      return {{calls: window.__calls.slice()}};
    }}""")
    assert not errors, errors
    assert out["calls"] == ["archivos"], out


def test_a_drag_on_the_header_never_maximizes(playwright_available):
    out, errors = _run(f"""async () => {{
      const {{head}} = window.__mk("archivos");
      ({_DRAG})(head);
      return {{calls: window.__calls.slice()}};
    }}""")
    assert not errors, errors
    assert out["calls"] == [], "a genuine drag must never be read as a maximize gesture"


def test_a_double_click_landing_on_the_headers_own_button_never_maximizes(playwright_available):
    """The title/⚙ buttons already open the aliases panel on click — a DOUBLE-click landing on THEM must not
    additionally toggle fullscreen, or double-clicking the title to rename/inspect it would also blow the
    card up. `.click()` (not the synthetic pointer-only `_TAP`) is what actually fires the button's own
    `onclick` in a headless page, which is the half this case needs to prove alongside "no maximize"."""
    out, errors = _run(f"""async () => {{
      const {{nameBtn}} = window.__mk("archivos");
      ({_DBLCLICK})(nameBtn);
      nameBtn.click();
      return {{calls: window.__calls.slice(), nameClicks: window.__nameClicks}};
    }}""")
    assert not errors, errors
    assert out["calls"] == [], "a double-click on the header's own button must not also maximize"
    assert out["nameClicks"] == 1, "and the button's own click must still fire"
