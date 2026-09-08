"""Dragging the orb with a chat column docked must not teleport it (V2-608, operator 2026-09-08).

MEASURED, the operator's report, second day running: «cuando pincho en el orbe, el ratón se va a donde
estaba el orbe antes de que hubiera salido la columna de la izquierda — se desplaza unos 200 píxeles. Y la
segunda vez que clico, el orbe se me ha movido fuera de la pantalla.»

Root cause, the SAME two-coordinate-systems defect F3 fixed for widget cards, still alive in the OTHER
drag path: `makeDraggable` (lib/draggable.js) serves the orb/camera/status chrome, and it took the grab
origin from `getBoundingClientRect()` (VIEWPORT pixels) and wrote it into `style.left` — which for an
element INSIDE `#desk` resolves against the DESK, because the desk's `transform` makes it the containing
block for its `position:fixed` descendants (V2-062, deliberate: the desktop moves as one unit). With a
420px column docked, the first real move of every drag added the column width once; the second drag added
it again — off the screen, exactly as reported. The persisted position had the same skew, so a spot saved
while docked came back wrong on every later load. And the clamp compared desk numbers against
`innerWidth`, so «never leaves the screen» did not mean «never leaves the desk».

The fix converts every read and write through the element's real containing block (`containerBox`): drag
deltas, clamps, the persisted position. An element mounted OUTSIDE any transformed ancestor (the feedback
button, the floating chat) gets the viewport box and keeps its old behaviour exactly.

RENDERED with the REAL lib/draggable.js, real pointer gestures, and the verbatim `#desk`/`.orbwrap` CSS —
the fixture lesson of V2-608: a harness whose DOM differs from the product's measures a different product.
"""
import asyncio
import pathlib

import pytest

DRAGGABLE = pathlib.Path("frontend/app/lib/draggable.js")

_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  :root{ --chatdock-l:0px; --chatdock-r:0px; }
  html,body{margin:0;height:100%;background:#0a1017}
  /* VERBATIM from styles.css, transform included — it makes #desk the containing block for fixed children. */
  #desk{position:fixed;top:0;bottom:0;left:var(--chatdock-l);right:var(--chatdock-r);transform:translate3d(0,0,0)}
  .orbwrap{position:fixed;left:50%;bottom:8px;transform:translateX(-50%);z-index:100000;display:flex;flex-direction:column;align-items:center}
  canvas#orb{width:148px;height:148px;background:#123}
  #freefloat{position:fixed;left:40px;top:40px;width:60px;height:60px;background:#331}
</style></head><body>
  <div id="desk"><div class="orbwrap" id="wrap"><canvas id="orb" width="148" height="148"></canvas></div></div>
  <div id="freefloat"></div>
</body></html>"""

_WIRE = """() => {
  window.__wrap = document.getElementById("wrap");
  window.__makeDraggable(window.__wrap, document.getElementById("orb"), "hb_pos_orb", "bl");
  window.__makeDraggable(document.getElementById("freefloat"), document.getElementById("freefloat"), "hb_pos_free", "tl");
  return true;
}"""

_READ = """() => {
  const w = document.getElementById("wrap").getBoundingClientRect();
  const d = document.getElementById("desk").getBoundingClientRect();
  const f = document.getElementById("freefloat").getBoundingClientRect();
  return {
    left: Math.round(w.left), centreX: Math.round(w.left + w.width / 2),
    deskLeft: Math.round(d.left), deskRight: Math.round(d.right),
    styleLeft: document.getElementById("wrap").style.left || "",
    stored: localStorage.getItem("hb_pos_orb"),
    freeLeft: Math.round(f.left), freeTop: Math.round(f.top),
  };
}"""


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright.async_api  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


def _module_source() -> str:
    return (DRAGGABLE.read_text(encoding="utf-8")
            + "\nwindow.__makeDraggable = makeDraggable; window.__resetDraggable = resetDraggable;\n")


async def _boot(pw):
    b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
    pg = await b.new_page(viewport={"width": 1400, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    await pg.route("http://zaelar.test/", lambda r: asyncio.ensure_future(
        r.fulfill(status=200, content_type="text/html", body=_HTML)))
    await pg.goto("http://zaelar.test/")
    await pg.add_script_tag(content=_module_source(), type="module")
    await pg.wait_for_function("() => !!window.__makeDraggable")
    await pg.evaluate(_WIRE)
    return b, pg, errors


async def _dock_left(pg, width):
    await pg.evaluate("""(w) => document.documentElement.style.setProperty("--chatdock-l", w + "px")""", width)


async def _drag(pg, selector, dx, dy):
    box = await pg.locator(selector).bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    await pg.mouse.move(x, y)
    await pg.mouse.down()
    for i in range(1, 6):
        await pg.mouse.move(x + dx * i / 5, y + dy * i / 5)
    await pg.mouse.up()


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


async def _noop(pg):
    pass


def test_a_drag_moves_the_orb_by_the_cursor_delta_with_a_column_docked(playwright_available):
    """Dock a 420px column, drag left by 150 — the orb moves 150, NOT 150 minus a column width. The
    reported symptom (a ~200px jump between cursor and orb on the first move) is this exact assertion."""
    async def dock(pg):
        await _dock_left(pg, 420)
    before, after = _run([dock, lambda pg: _drag(pg, "#orb", -150, 0)])
    delta = after["centreX"] - before["centreX"]
    assert abs(delta - (-150)) <= 4, f"drag of -150 moved the orb by {delta} (the column width is leaking in)"
    assert not after["errors"], f"page errors: {after['errors']}"


def test_two_consecutive_drags_do_not_accumulate_an_offset(playwright_available):
    """The second reported click sent the orb OFF-SCREEN: each drag re-added the dock offset. Two equal
    drags must give exactly twice the movement, and the orb must still be on the desk."""
    async def dock(pg):
        await _dock_left(pg, 420)
    before, one, two = _run([dock,
                             lambda pg: _drag(pg, "#orb", -100, 0),
                             lambda pg: _drag(pg, "#orb", -100, 0)])
    total = two["centreX"] - before["centreX"]
    assert abs(total - (-200)) <= 6, f"two drags of -100 moved the orb by {total} in total"
    assert two["left"] >= two["deskLeft"] - 2, f"the orb left the desk: {two}"


def test_the_orb_cannot_be_dragged_off_the_desk(playwright_available):
    """The clamp is the DESK's edge, not the window's: with a column docked, dragging hard left parks the
    orb at the desk's left edge — never under the column, never off-screen."""
    async def dock_and_yank(pg):
        await _dock_left(pg, 420)
        await _drag(pg, "#orb", -2000, 0)
    (after,) = _run([dock_and_yank])
    assert after["left"] >= after["deskLeft"] - 2, f"the orb went under the column/off-screen: {after}"
    assert after["left"] <= after["deskLeft"] + 8, f"a hard-left drag should park at the desk edge: {after}"


def test_a_position_saved_while_docked_comes_back_where_it_was(playwright_available):
    """The persisted position is container-relative now: saved with a column docked, re-applied on the next
    load with the same column, the orb renders at the SAME viewport spot — the old shape shifted it by the
    column width on every later visit."""
    async def dock_drag(pg):
        await _dock_left(pg, 420)
        await _drag(pg, "#orb", -180, 0)
    async def reload_apply(pg):
        # A fresh load with the same dock: wipe the inline styles the drag wrote, then re-wire — apply()
        # reads the stored position back exactly as the real page does at mount.
        await pg.evaluate("""() => {
          const w = window.__wrap;
          for (const p of ["left", "right", "top", "bottom", "transform"]) w.style[p] = "";
          window.__makeDraggable(w, document.getElementById("orb"), "hb_pos_orb", "bl");
        }""")
    saved, restored = _run([dock_drag, reload_apply])
    assert saved["stored"], "the drag must persist a position"
    assert abs(restored["centreX"] - saved["centreX"]) <= 2, \
        f"restored at {restored['centreX']}, was saved at {saved['centreX']} — the store is in the wrong space"


def test_an_element_outside_the_desk_is_untouched_by_the_dock(playwright_available):
    """The feedback button and the floating chat live OUTSIDE #desk: their coordinate space is the viewport,
    column or no column, and their drags must behave exactly as before this fix."""
    async def dock(pg):
        await _dock_left(pg, 420)
    before, after = _run([dock, lambda pg: _drag(pg, "#freefloat", 120, 60)])
    assert abs((after["freeLeft"] - before["freeLeft"]) - 120) <= 4, f"free element x: {before} -> {after}"
    assert abs((after["freeTop"] - before["freeTop"]) - 60) <= 4, f"free element y: {before} -> {after}"
    assert not after["errors"], f"page errors: {after['errors']}"
