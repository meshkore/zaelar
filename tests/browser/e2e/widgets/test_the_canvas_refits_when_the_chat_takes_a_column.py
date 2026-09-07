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
  /* VERBATIM from styles.css, transform included — it is the whole point: a transformed ancestor becomes the
     containing block for `position:fixed` descendants, so `.hb-stage{inset:0}` resolves against #desk and the
     cards are written in DESK coordinates. The first fixture made #wstage a SIBLING of #desk; the two
     coordinate systems then coincided, and the suite measured a product that does not exist. */
  #desk{position:fixed;top:0;bottom:0;left:var(--chatdock-l);right:var(--chatdock-r);transform:translate3d(0,0,0)}
  #chatwall{position:fixed;top:0;bottom:0;width:0;display:none;background:#111}
  #chatwall.open{display:block}
  #chatwall.dock-left{left:0} #chatwall.dock-right{right:0}
</style></head><body>
  <div id="desk"><div id="wstage"></div></div><div id="activity"></div>
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
  d._uiAudit = () => {};
  d.z = 20;
  const mk = (id, left, top, w, h) => {
    const c = document.createElement("div");
    c.className = "hb-win"; c.dataset.wid = id;
    c.style.cssText = `position:absolute;left:${left}px;top:${top}px;width:${w}px;height:${h}px;box-sizing:border-box;background:#223`;
    // The real card chrome: a nine-dot grip and the header strip, both drag handles since V2-608 F6.
    const grip = document.createElement("button");
    grip.className = "hb-grip";
    grip.style.cssText = "position:absolute;top:7px;left:8px;width:26px;height:26px";
    const head = document.createElement("div");
    head.className = "hb-head";
    head.style.cssText = "position:absolute;top:6px;left:40px;right:70px;height:24px";
    c.append(grip, head);
    d.stage.appendChild(c);
    d.wins.set(id, {card:c, head});
    d._wireDrag(c);                      // the product decides which parts of the chrome are handles
    return c;
  };
  d._watchCanvas();            // the REAL registration the constructor calls — not a copy of it
  window.__d = d;
  window.__mk = mk;
  return true;
})()"""

_READ = """() => {
  const out = {};
  const d = document.getElementById("desk").getBoundingClientRect();
  window.__d.wins.forEach((w, id) => {
    const r = w.card.getBoundingClientRect();          // VIEWPORT — what the operator's eye sees
    out[id] = {left:Math.round(r.left), top:Math.round(r.top),
               right:Math.round(r.right), bottom:Math.round(r.bottom),
               w:Math.round(r.width), h:Math.round(r.height),
               styleLeft: parseInt(w.card.style.left)||0};
  });
  out.__desk = {left:Math.round(d.left), right:Math.round(d.right),
                top:Math.round(d.top), bottom:Math.round(d.bottom), w:Math.round(d.width)};
  out.__canvas = window.__d.canvas();                  // DESK coordinates, like style.left
  out.__persisted = window.__persisted || 0;
  return out;
}"""


# Assertions are made in VIEWPORT space against the DESK's own box: that is what «inside the visible area»
# means to the person looking at the screen, and it stays true whatever coordinate system the code uses
# internally. Asserting the internal one is how the first version of this suite passed while the product
# pushed every card off the right of the screen.
def _inside(card, desk, slack=2):
    return (card["left"] >= desk["left"] - slack and card["right"] <= desk["right"] + slack
            and card["bottom"] <= desk["bottom"] + slack)


def _module_source() -> str:
    """desktop.js with its top-of-file imports stubbed — the geometry under test does not use i18n, and this
    page (a single `route`-mocked HTML string, no static file server behind it) cannot resolve a REAL import of
    ../core/*.js. A regex anchored to ONE specific import line (V2-613 added a second, `store.js`, for
    `ctx.lang`) silently stops matching new ones and leaves an unresolved module specifier that fails the whole
    script tag — every `window.__Desktop` wait then times out with no error a human would connect to i18n."""
    src = DESKTOP.read_text(encoding="utf-8")
    src = re.sub(r'^import \{ t as tr \}.*$', 'const tr = (k) => k;', src, count=1, flags=re.M)
    src = re.sub(r'^import \* as store from .*$', 'const store = { lang: () => "en" };', src, count=1, flags=re.M)
    # A leftover `^import ` line is an UNRESOLVED module specifier on this route-mocked page (no static file
    # server behind it) — the exact class of failure a NEW import silently reintroduces if this function is not
    # updated alongside it. Fail loud here instead of a 30s `wait_for_function` timeout with no clue why.
    leftover = re.findall(r'^import .*$', src, flags=re.M)
    assert not leftover, f"_module_source() does not stub: {leftover} — every import needs a stub line above"
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
    assert after["__desk"]["left"] == 600, after["__desk"]
    assert _inside(after["results"], after["__desk"]), \
        f"the card is not inside the visible desk: {after['results']} vs desk {after['__desk']}"
    assert after["errors"] == [], after["errors"]


def test_a_card_past_the_new_right_edge_is_pulled_back_whole(playwright_available):
    """The screenshot's actual complaint: the card on the right is cut off by the window edge. Nothing moved it,
    because the rail clamp only ever pushed cards RIGHTWARDS and the chat dock announced nothing at all."""
    after = _run([_two_cards, lambda pg: _dock_left(pg, 600)])[1]
    d = after["__desk"]
    assert after["navegador"]["right"] <= d["right"], \
        f"still hanging off the right edge of the screen: {after['navegador']} vs desk {d}"
    assert _inside(after["navegador"], d), after["navegador"]


def test_a_card_too_wide_for_what_is_left_is_SHRUNK_not_just_moved(playwright_available):
    """autofit AND autoresize: with 786px of canvas, a 1200px card cannot be fixed by moving it."""
    async def wide(pg):
        await pg.evaluate("""() => { window.__mk("results", 60, 100, 1200, 300); window.__d.fitAll(); }""")
    after = _run([wide, lambda pg: _dock_left(pg, 600)])[1]
    d = after["__desk"]
    assert after["results"]["w"] <= d["w"], after["results"]
    assert _inside(after["results"], d), after["results"]


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
    # Compared in DESK coordinates: the desk itself moves back left when the column is released, so the whole
    # stage translates with it — that is CSS doing its job, not the refit moving anything.
    assert freed["results"]["styleLeft"] == docked["results"]["styleLeft"], "a legal card must not be moved again"
    assert freed["navegador"]["styleLeft"] == docked["navegador"]["styleLeft"], freed["navegador"]


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


# ── A FLOATING wall is not a column (V2-608, operator the same day) ─────────────────────────────────────────
async def _float_left(pg):
    """Open the chat WITHOUT docking it — the default: a small panel parked near the left edge. No
    `--chatdock-l` is published, because `setReserve()` only publishes one for a wall that is open AND docked."""
    await pg.evaluate("""() => {
      const cw = document.getElementById("chatwall");
      cw.style.cssText = "position:fixed;left:18px;top:230px;width:320px;height:480px;background:#111";
      cw.classList.add("open");
      document.dispatchEvent(new CustomEvent("hb:canvas-resized", {detail:{side:null}}));
    }""")
    await pg.wait_for_timeout(80)


def test_a_FLOATING_chat_does_not_shrink_the_canvas(playwright_available):
    """His report, 2026-09-07: «simplemente le he dicho que abra el chat… no lo hemos pegado a la barra de la
    izquierda para que se haga una columna, y ha movido el resto de objetos a la derecha. Eso no había pasado
    nunca.»

    The first version of `canvas()` read the WALL's bounding rect — inherited from `arrange()`, whose comment
    said «docked/floating on the LEFT». For a deliberate tiling gesture that is a nicety; for a refit that runs
    on every canvas change it means merely OPENING the chat rebuilds the desktop. The canvas is the DESK, and
    the desk is inset by `--chatdock-l/r`, which only a docked wall publishes."""
    steps = _run([_two_cards, _float_left])
    before, after = steps[0], steps[1]
    assert after["__canvas"]["x0"] == before["__canvas"]["x0"], \
        f"a floating panel moved the canvas edge: {before['__canvas']} → {after['__canvas']}"
    assert after["__desk"]["left"] == before["__desk"]["left"], "the desk itself must not move"
    for wid in ("results", "navegador"):
        assert after[wid]["left"] == before[wid]["left"] and after[wid]["top"] == before[wid]["top"], \
            f"{wid} was moved by a chat that took no column: {before[wid]} → {after[wid]}"
        assert after[wid]["w"] == before[wid]["w"], f"{wid} was resized for nothing: {after[wid]}"


def test_the_canvas_is_measured_in_DESK_coordinates(playwright_available):
    """The property the whole fix rests on, stated where it can fail loudly.

    `#wstage` is a child of `#desk`, and `#desk` carries `transform: translate3d(0,0,0)` — which makes it the
    containing block for every `position:fixed` descendant, `.hb-stage{inset:0}` included. So `style.left` is
    measured from the DESK, and the stage slides right on its own when a column insets `#desk` in CSS.

    Measured on the real page: a card at `style.left:100px` renders at viewport 115 undocked and at 535 with a
    420px column, with `style.left` untouched. Clamping `style.left` against a VIEWPORT number therefore adds
    the column width a second time — which is exactly what the first cut of V2-608 did."""
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b, pg, _ = await _boot(pw)
            await _two_cards(pg)
            await _dock_left(pg, 600)
            out = await pg.evaluate("""() => {
              const d = document.getElementById("desk").getBoundingClientRect();
              const c = window.__d.canvas();
              const card = window.__d.wins.get("results").card;
              return {deskLeft: Math.round(d.left), deskW: Math.round(d.width), c,
                      styleLeft: parseInt(card.style.left)||0,
                      renderedLeft: Math.round(card.getBoundingClientRect().left)};
            }""")
            await b.close()
            return out
    m = asyncio.run(go())
    pad = 14
    assert m["c"]["x0"] == pad, f"the canvas origin is the DESK's own left, not the window's: {m}"
    assert m["c"]["x1"] == m["deskW"] - pad, m
    # And the two coordinate systems really do differ by the column, which is what makes this load-bearing.
    assert m["renderedLeft"] - m["styleLeft"] == m["deskLeft"], m


# ── Dragging: desk coordinates, and the whole header is a handle (V2-608 F3/F6) ─────────────────────────────
def _grab(sel):
    """Press on `sel`, move 120px right / 60px down, release — a real pointer gesture, real hit-testing."""
    async def step(pg):
        box = await pg.locator(sel).bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        await pg.mouse.move(cx, cy)
        await pg.mouse.down()
        await pg.mouse.move(cx + 20, cy + 10)      # past the 4px tap threshold
        await pg.mouse.move(cx + 120, cy + 60)
        await pg.mouse.up()
        await pg.wait_for_timeout(60)
    return step


def test_grabbing_a_card_with_a_column_docked_does_not_TELEPORT_it(playwright_available):
    """His report: «cuando pincho en el botón para moverlo, la manita aparece desplazada 100 o 200 píxeles a la
    izquierda del widget».

    `_wireDrag` measured the grab offset from `getBoundingClientRect()` (VIEWPORT) and wrote the result straight
    into `style.left` (DESK). With a column docked the two differ by its width, so the card jumped sideways by
    exactly that on the first pointermove — and was silently correct whenever nothing was docked."""
    async def dock(pg):
        await _dock_left(pg, 600)

    steps = _run([_two_cards, dock, _grab('[data-wid="results"] .hb-grip')])
    docked, dragged = steps[1], steps[2]
    dx = dragged["results"]["left"] - docked["results"]["left"]
    dy = dragged["results"]["top"] - docked["results"]["top"]
    assert 90 <= dx <= 150, f"the card did not follow the pointer: moved {dx}px for a 120px drag"
    assert 40 <= dy <= 90, f"vertical drift: {dy}"
    assert _inside(dragged["results"], dragged["__desk"]), dragged["results"]


def test_the_WHOLE_HEADER_drags_the_card_not_only_the_nine_dots(playwright_available):
    """Operator, 2026-09-07: «cualquier cajita en Windows o en Mac se puede mover pinchando en cualquier punto de
    la barra superior, salvo en sus botones». Default for every widget, system-made or user-made."""
    steps = _run([_two_cards, _grab('[data-wid="results"] .hb-head')])
    before, after = steps[0], steps[1]
    dx = after["results"]["left"] - before["results"]["left"]
    assert 90 <= dx <= 150, f"the header did not drag the card: moved {dx}px"


def test_a_TAP_on_the_header_does_not_move_the_card(playwright_available):
    """The 4px threshold. The header carries the title button (it opens the aliases panel), so a click has to
    stay a click — that is what the old `stopPropagation` was protecting, and it must survive the change."""
    async def tap(pg):
        box = await pg.locator('[data-wid="results"] .hb-head').bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        await pg.mouse.move(cx, cy)
        await pg.mouse.down()
        await pg.mouse.move(cx + 2, cy + 1)
        await pg.mouse.up()
        await pg.wait_for_timeout(60)
    steps = _run([_two_cards, tap])
    assert steps[1]["results"]["left"] == steps[0]["results"]["left"], "a tap moved the card"
    # And it must not have been recorded as a move: on a 5px grid a 3px drag can snap back to the same pixel,
    # so position alone would let «every tap is a drag» through. Persisting is the signal that cannot round away.
    assert steps[1]["__persisted"] == 0, "a tap was persisted as a move"


def test_a_new_card_placed_with_a_column_docked_does_not_land_on_an_existing_one(playwright_available):
    """`_obstacles()` returned VIEWPORT rects while `_place()` scans in DESK coordinates, so with a column docked
    every obstacle was reported a column-width to the right of where it actually is — and the scan happily put a
    new card on top of one it thought was somewhere else. Silently correct whenever nothing is docked, which is
    why it survived until docking became a real workflow."""
    async def place_with_dock(pg):
        await _dock_left(pg, 600)
        await pg.evaluate("""() => {
          const c = window.__mk("agenda", 0, 0, 300, 200);
          window.__d._place(c);                       // the real placement scan
        }""")
        await pg.wait_for_timeout(60)

    after = _run([_two_cards, place_with_dock])[1]
    a, others = after["agenda"], [after["results"], after["navegador"]]
    for o in others:
        overlap = not (a["right"] <= o["left"] or a["left"] >= o["right"]
                       or a["bottom"] <= o["top"] or a["top"] >= o["bottom"])
        assert not overlap, f"placed on top of an existing card: {a} vs {o}"
    assert _inside(a, after["__desk"]), a
