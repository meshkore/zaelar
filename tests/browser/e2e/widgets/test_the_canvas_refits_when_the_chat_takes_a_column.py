"""The desktop must REFIT when the canvas changes shape (V2-608).

MEASURED, operator's screenshot 2026-09-07: he dragged the chat wall to the left edge. It docked correctly into a
full-height column — and every widget stayed exactly where it was. `#desk` follows `--chatdock-l/r` in CSS, but
the cards live on `.hb-stage` (`inset:0`) in VIEWPORT coordinates, so the desk shrank underneath them: one card
ended up behind the chat column and the one on the right was cut off by the window edge, unreachable.

Three ways the canvas can change shape, and until this only one of them said anything:
  · the widget rail folds/unfolds (V2-538) — announced, but the listener only ever shoved cards RIGHTWARDS: it
    never resized an oversized card and never pulled one back from the right edge
  · the chat wall docks / undocks / is dragged wider — announced NOTHING
  · the browser window is resized — not listened to anywhere

RENDERED, not read. A source test would say the listener exists; only layout says the card ended up inside. The
`canvas()` rectangle is the thing under test: it already existed, inline inside `arrange()`, which was the single
gesture on the whole canvas that knew a chat column could be there.
"""
import asyncio
import pathlib
import re

import pytest

DESKTOP = pathlib.Path("frontend/app/widgets/desktop.js")

_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  :root{ --chatdock-l:0px; --chatdock-r:0px; }
  html,body{margin:0;height:100%;background:#0a1017}
  #desk{position:fixed;top:0;bottom:0;left:var(--chatdock-l);right:var(--chatdock-r)}
  #chatwall{position:fixed;top:0;bottom:0;width:0;display:none;background:#111}
  #chatwall.open{display:block}
  #chatwall.dock-left{left:0} #chatwall.dock-right{right:0}
</style></head><body>
  <div id="desk"></div><div id="wstage"></div><div id="activity"></div>
  <div id="chatwall"></div>
</body></html>"""

# Two cards placed for a FULL-WIDTH canvas: one on the left, one wide one out at the right. Exactly the shape of
# the screenshot — nothing is wrong with either until the canvas loses 600px on the left.
_SETUP = """(async () => {
  const D = window.__Desktop;
  const d = Object.create(D.prototype);
  d.stage = document.getElementById("wstage");
  d.wins = new Map();
  d.tile = {w:400, h:340, top:70, pad:14};
  d.grid = 5;
  d._meta = {results:{}, navegador:{min:{w:520, h:300}}};
  d._persist = () => { window.__persisted = (window.__persisted||0) + 1; };
  const mk = (id, left, top, w, h) => {
    const c = document.createElement("div");
    c.className = "hb-win"; c.dataset.wid = id;
    c.style.cssText = `position:absolute;left:${left}px;top:${top}px;width:${w}px;height:${h}px;box-sizing:border-box`;
    d.stage.appendChild(c);
    d.wins.set(id, {card:c});
    return c;
  };
  d._watchCanvas();            // the REAL registration the constructor calls — not a copy of it
  window.__d = d;
  window.__mk = mk;
  return true;
})()"""

_READ = """() => {
  const out = {};
  window.__d.wins.forEach((w, id) => {
    const r = w.card.getBoundingClientRect();
    out[id] = {left:Math.round(r.left), top:Math.round(r.top),
               right:Math.round(r.right), bottom:Math.round(r.bottom),
               w:Math.round(r.width), h:Math.round(r.height)};
  });
  out.__canvas = window.__d.canvas();
  return out;
}"""


def _module_source() -> str:
    """desktop.js with its single import stubbed — the geometry under test does not use i18n."""
    src = DESKTOP.read_text(encoding="utf-8")
    src = re.sub(r'^import \{ t as tr \}.*$', 'const tr = (k) => k;', src, count=1, flags=re.M)
    return src + "\nwindow.__Desktop = Desktop;\n"


async def _boot(pw):
    b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
    pg = await b.new_page(viewport={"width": 1400, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    await pg.route("http://zaelar.test/", lambda r: asyncio.ensure_future(
        r.fulfill(status=200, content_type="text/html", body=_HTML)))
    await pg.goto("http://zaelar.test/")
    await pg.add_script_tag(content=_module_source(), type="module")
    await pg.wait_for_function("() => !!window.__Desktop")
    await pg.evaluate(_SETUP)
    return b, pg, errors


async def _dock_left(pg, width):
    """What ChatWall.setReserve() does to the DOM, and the event it now fires."""
    await pg.evaluate("""(w) => {
      const cw = document.getElementById("chatwall");
      cw.style.width = w + "px";
      cw.classList.add("open", "dock-left");
      document.documentElement.style.setProperty("--chatdock-l", w + "px");
      document.dispatchEvent(new CustomEvent("hb:canvas-resized", {detail:{side:"left"}}));
    }""", width)
    await pg.wait_for_timeout(80)


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright.async_api  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


def _run(steps):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b, pg, errors = await _boot(pw)
            out = []
            for step in steps:
                await step(pg)
                m = await pg.evaluate(_READ)
                m["errors"] = errors
                out.append(m)
            await b.close()
            return out
    return asyncio.run(go())


async def _two_cards(pg):
    await pg.evaluate("""() => {
      window.__mk("results", 80, 100, 400, 300);      // comfortably left
      window.__mk("navegador", 900, 120, 460, 320);   // out at the right, fine at 1400px wide
      window.__d.fitAll();
      window.__persisted = 0;
    }""")


def test_a_card_behind_the_new_chat_column_is_brought_out(playwright_available):
    """The left card sits at x=80. Dock a 600px chat column and it is UNDER it — the one place he cannot see it."""
    steps = _run([_two_cards, lambda pg: _dock_left(pg, 600)])
    before, after = steps[0], steps[1]
    assert before["results"]["left"] == 80, before["results"]
    assert after["__canvas"]["x0"] >= 600, after["__canvas"]
    assert after["results"]["left"] >= after["__canvas"]["x0"], \
        f"the card stayed under the chat column: {after['results']}"
    assert after["errors"] == [], after["errors"]


def test_a_card_past_the_new_right_edge_is_pulled_back_whole(playwright_available):
    """The screenshot's actual complaint: the card on the right is cut off by the window edge. Nothing moved it,
    because the rail clamp only ever pushed cards RIGHTWARDS and the chat dock announced nothing at all."""
    after = _run([_two_cards, lambda pg: _dock_left(pg, 600)])[1]
    c = after["__canvas"]
    assert after["navegador"]["right"] <= c["x1"] + 1, f"still hanging off the edge: {after['navegador']}"
    assert after["navegador"]["left"] >= c["x0"] - 1, after["navegador"]
    assert after["navegador"]["bottom"] <= c["y1"] + 1, after["navegador"]


def test_a_card_too_wide_for_what_is_left_is_SHRUNK_not_just_moved(playwright_available):
    """autofit AND autoresize: with 786px of canvas, a 1200px card cannot be fixed by moving it."""
    async def wide(pg):
        await pg.evaluate("""() => { window.__mk("results", 60, 100, 1200, 300); window.__d.fitAll(); }""")
    after = _run([wide, lambda pg: _dock_left(pg, 600)])[1]
    c = after["__canvas"]
    assert after["results"]["w"] <= (c["x1"] - c["x0"]) + 1, after["results"]
    assert after["results"]["right"] <= c["x1"] + 1, after["results"]


def test_the_shrinking_stops_at_the_widget_OWN_minimum(playwright_available):
    """«respect min height and width per widget». `navegador` declares min 520×300; squeezed to a 300px canvas it
    must stop at 520 and let the card overflow the strip, never collapse into an unusable sliver."""
    async def one(pg):
        await pg.evaluate("""() => { window.__mk("navegador", 60, 100, 800, 400); window.__d.fitAll(); }""")
    after = _run([one, lambda pg: _dock_left(pg, 1100)])[1]
    assert after["navegador"]["w"] == 520, f"its own minimum, not the global floor: {after['navegador']}"
    assert after["navegador"]["h"] >= 300, after["navegador"]


def test_a_widget_with_no_declared_minimum_uses_the_canvas_floor(playwright_available):
    """`results` declares none, so it may go down to 240 — and no further."""
    async def one(pg):
        await pg.evaluate("""() => { window.__mk("results", 60, 100, 900, 400); window.__d.fitAll(); }""")
    after = _run([one, lambda pg: _dock_left(pg, 1200)])[1]
    assert after["results"]["w"] == 240, after["results"]


def test_undocking_does_not_drag_the_cards_back(playwright_available):
    """Refitting is a REPAIR, not a layout engine. Releasing the column gives the room back; it must not also
    undo where he put things — a card that is already legal is left exactly alone."""
    async def undock(pg):
        await pg.evaluate("""() => {
          document.getElementById("chatwall").classList.remove("open", "dock-left");
          document.documentElement.style.setProperty("--chatdock-l", "0px");
          document.dispatchEvent(new CustomEvent("hb:canvas-resized", {detail:{side:null}}));
        }""")
        await pg.wait_for_timeout(80)
    steps = _run([_two_cards, lambda pg: _dock_left(pg, 600), undock])
    docked, freed = steps[1], steps[2]
    assert freed["results"]["left"] == docked["results"]["left"], "a legal card must not be moved again"
    assert freed["navegador"]["left"] == docked["navegador"]["left"], freed["navegador"]


def test_nothing_is_persisted_when_nothing_had_to_move(playwright_available):
    """A refit that changed nothing must not write the desktop — the dock drag fires this continuously, and a
    save per pointer frame is how a smooth drag becomes a stutter and the server gets flooded."""
    async def measure(pg):
        await pg.evaluate("""() => {
          window.__mk("results", 80, 100, 300, 200);
          window.__d.fitAll();
          window.__persisted = 0;
          window.__d.fitAll(); window.__d.fitAll();
          window.__quiet = window.__persisted;
        }""")
    _run([measure])
    # asserted inside the page; surfaced here
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b, pg, _ = await _boot(pw)
            await measure(pg)
            n = await pg.evaluate("() => window.__quiet")
            await b.close()
            return n
    assert asyncio.run(go()) == 0
