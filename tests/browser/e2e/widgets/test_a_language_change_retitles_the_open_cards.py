"""A language change repaints the card's own HEADER, not only its body (V2-694).

V2-613 gave a widget's INSIDE a live language switch: `Desktop.relanguage()` re-invokes each open widget's
`render()` with the same cached data, and `ctx.t` resolves against whatever bundle is active now. What it could
not cover is the one string the widget does not draw — the card's TITLE, which the canvas paints from the
registry it fetched once at boot. Until this batch that title was a constant (the manifest's `name`, Castilian
for all fifteen), so caching it was free; now it is a translated string, and a cache that never drops leaves
every card titled in the language the operator just left.

RENDERED, not read: a source scan can prove the fetch line exists and prove nothing about whether the header
actually changes. The `Desktop` is built the way its neighbour test builds one — `Object.create(prototype)` past
a constructor that talks to the server — with `fetch` driven by hand, so WHICH requests go out and WHEN is
observable, which is the whole question here.
"""
import asyncio
import json
import pathlib
import re

import pytest

DESKTOP = pathlib.Path("frontend/app/widgets/desktop.js")

_HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body><div id="wstage"></div></body></html>"""

# A Desktop with exactly the collaborators `relanguage` touches. The registry answers in whatever language
# `window.__lang` currently says, which is what the real endpoint does (`widgets/registry.py::display_name`).
_SETUP = """(async () => {
  const D = window.__Desktop;
  const d = Object.create(D.prototype);
  d.stage = document.getElementById("wstage");
  d.wins = new Map();
  d._persist = () => {};
  window.__lang = "es";
  window.__fetched = [];
  const NAMES = {es: {mensajeria: "Mensajería"}, en: {mensajeria: "Messages"}};
  window.fetch = async (url) => {
    window.__fetched.push(String(url));
    const name = NAMES[window.__lang].mensajeria;
    if(String(url).includes("/widgets/registry"))
      return { json: async () => ({registry: [{id: "mensajeria", name, aliases: [name]}]}) };
    if(String(url) === "/widgets")
      return { json: async () => ({widgets: [{id: "mensajeria", name, aliases: [name]}]}) };
    return { json: async () => ({}) };
  };
  // A mounted card, the way `show()` leaves one: a header with the name button, and a module that renders.
  window.__card = async (id) => {
    const card = document.createElement("div"); card.className = "hb-win";
    const head = document.createElement("div"); head.className = "hb-head";
    const mark = document.createElement("span"); mark.className = "hb-mark";
    const nameBtn = document.createElement("button"); nameBtn.className = "hb-name";
    head.append(mark, nameBtn); card.appendChild(head);
    const body = document.createElement("div"); d.stage.append(card); card.appendChild(body);
    const renders = [];
    const w = {card, body, head, mark, nameBtn, base: id, _renders: renders,
               _lastData: {n: 1}, _ctx: {}, _mod: {render: (el, data) => renders.push(data)}};
    d.wins.set(id, w);
    await d._applyName(w);
    return w;
  };
  window.__d = d;
  return true;
})()"""


def _module_source() -> str:
    """desktop.js with its top-of-file imports stubbed — the route-mocked page has no static server, so a real
    `../core` import kills the whole script tag in silence (the V2-613 trap, documented by its neighbours)."""
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


def test_an_open_cards_title_follows_the_language(playwright_available):
    """The operator's own report, reduced to its smallest form: a card open, the language moves, and the header
    still says the old word."""
    out, errors = _run("""(async () => {
      const d = window.__d;
      const w = await window.__card("mensajeria");
      const before = w.nameBtn.textContent;
      window.__lang = "en";                       // the ⚙ switch: the ENDPOINT now answers in English
      d.relanguage();
      await new Promise(r => setTimeout(r, 30));
      return {before, after: w.nameBtn.textContent, renders: w._renders.length};
    })()""")
    assert not errors, errors
    assert out["before"] == "Mensajería"
    assert out["after"] == "Messages", \
        "the card kept the title of the language the operator just left — the registry is cached and nothing dropped it"
    assert out["renders"] >= 1, "…and the widget's own body still re-renders (the V2-613 half must not regress)"


def test_the_monogram_follows_the_title(playwright_available):
    """The header's mark is DERIVED from the text beside it (V2-689) precisely so the two can never disagree —
    which only holds if the mark is recomputed when the title changes."""
    out, errors = _run("""(async () => {
      const d = window.__d;
      const w = await window.__card("mensajeria");
      const before = w.mark.textContent;
      window.__lang = "en";
      d.relanguage();
      await new Promise(r => setTimeout(r, 30));
      return {before, after: w.mark.textContent};
    })()""")
    assert not errors, errors
    assert out["before"] == "M" and out["after"] == "M", out          # both languages start with M here…
    # …so the real claim is the one above it; this case exists to catch the mark being left BLANK or stale-typed
    # when the title is rewritten, which is what a hand-maintained second table would do.


def test_the_compact_index_cache_is_dropped_too(playwright_available):
    """`_resolve`/`_meta` cache `GET /widgets`, and that row carries `name` as well (`_index_row` builds it from
    the very same identity). Dropping only the registry would leave a second, staler copy of every name one
    lookup away."""
    out, errors = _run("""(async () => {
      const d = window.__d;
      await window.__card("mensajeria");
      await d._resolve("mensajeria");                       // fills _ids/_meta from GET /widgets
      const cachedBefore = (d._meta || {}).mensajeria.name;
      window.__lang = "en";
      d.relanguage();
      await new Promise(r => setTimeout(r, 30));
      await d._resolve("mensajeria");
      return {cachedBefore, cachedAfter: (d._meta || {}).mensajeria.name,
              asked: window.__fetched.filter(u => u === "/widgets").length};
    })()""")
    assert not errors, errors
    assert out["cachedBefore"] == "Mensajería"
    assert out["cachedAfter"] == "Messages", "the compact index kept a stale name after the language moved"
    assert out["asked"] == 2, f"the index should be re-fetched exactly once after the switch: {out['asked']}"
