"""A RESET sends the orb back to its birthplace (V2-608, operator 2026-09-07).

«Cuando se hace un reset, quiero que el orbe vuelva a su posición inicial, aparte ya del resto de
operaciones que hacemos.» The Reset button already clears the canvas, the debug log and the chat history
(`_clearCanvasAndLog()`, session-lk.js) — but a dragged orb stayed wherever the drag left it, and the
persisted `hb_pos_orb` would put it back there on every future page load too.

The restore is `resetDraggable()` in lib/draggable.js — the UNDO of makeDraggable: forget the persisted
position AND drop the inline styles the drag wrote, so `.orbwrap`'s own CSS centres it on the desk again.
Both halves are load-bearing: clearing only the styles leaves the old position in storage, and the next
page load re-applies it (makeDraggable's apply() reads the key at wire-time).

RENDERED, not read: the REAL lib/draggable.js is mounted (it has zero imports), the orb is dragged with
real pointer gestures, and «home» is asserted as geometry — the centre of the DESK, not of the window,
because `.orbwrap` lives inside `#desk` and the transformed desk is the containing block for its
`position:fixed` (the V2-608 lesson: a fixture with the wrong DOM measures a different product).
"""
import asyncio
import pathlib

import pytest

DRAGGABLE = pathlib.Path("frontend/app/lib/draggable.js")
ORB = pathlib.Path("frontend/app/components/Orb.js")
SESSION_LK = pathlib.Path("frontend/app/services/session-lk.js")

_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  :root{ --chatdock-l:0px; --chatdock-r:0px; }
  html,body{margin:0;height:100%;background:#0a1017}
  /* VERBATIM from styles.css, transform included: #desk is the containing block for fixed descendants,
     so .orbwrap's left:50% is 50% OF THE DESK — the reset must return the orb to THIS rule's position. */
  #desk{position:fixed;top:0;bottom:0;left:var(--chatdock-l);right:var(--chatdock-r);transform:translate3d(0,0,0)}
  .orbwrap{position:fixed;left:50%;bottom:8px;transform:translateX(-50%);z-index:100000;display:flex;flex-direction:column;align-items:center}
  canvas#orb{width:148px;height:148px;background:#123}
</style></head><body>
  <div id="desk"><div class="orbwrap" id="wrap"><canvas id="orb" width="148" height="148"></canvas></div></div>
</body></html>"""

_WIRE = """() => {
  window.__wrap = document.getElementById("wrap");
  window.__moved = window.__makeDraggable(window.__wrap, document.getElementById("orb"), "hb_pos_orb", "bl");
  return true;
}"""

_READ = """() => {
  const w = document.getElementById("wrap").getBoundingClientRect();
  const d = document.getElementById("desk").getBoundingClientRect();
  return {
    centreOffset: Math.round((w.left + w.width / 2) - (d.left + d.width / 2)),
    fromBottom: Math.round(d.bottom - w.bottom),
    stored: localStorage.getItem("hb_pos_orb"),
    inlineLeft: document.getElementById("wrap").style.left || "",
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


async def _drag_orb(pg, dx, dy):
    """A real pointer gesture on the orb canvas — the only way makeDraggable moves anything."""
    box = await pg.locator("#orb").bounding_box()
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


async def _reset(pg):
    await pg.evaluate("""() => window.__resetDraggable(window.__wrap, "hb_pos_orb")""")


def test_a_dragged_orb_goes_home_on_reset(playwright_available):
    """Drag the orb far off-centre, reset — it is centred on the desk again and the memory of the drag is gone."""
    before, dragged, after = _run([_noop, lambda pg: _drag_orb(pg, -320, -180), _reset])
    assert dragged["centreOffset"] < -200, f"the drag itself must move the orb (got {dragged})"
    assert dragged["stored"], "makeDraggable must persist the dragged position"
    assert abs(after["centreOffset"]) <= 2, f"after reset the orb must be centred on the desk (got {after})"
    assert after["fromBottom"] == 8, f"after reset the orb sits 8px off the desk bottom (got {after})"
    assert after["stored"] is None, "the persisted position must be forgotten, or the next page load undoes the reset"
    assert after["inlineLeft"] == "", "the drag's inline styles must be gone — CSS owns the position again"
    assert not after["errors"], f"page errors: {after['errors']}"


def test_a_position_from_a_previous_visit_goes_home_too(playwright_available):
    """The persisted position is applied at wire-time (apply() in makeDraggable) — reset must beat that path too."""
    async def seed_and_rewire(pg):
        await pg.evaluate("""() => {
          localStorage.setItem("hb_pos_orb", JSON.stringify({left: 60, bottom: 300}));
          window.__makeDraggable(window.__wrap, document.getElementById("orb"), "hb_pos_orb", "bl");
        }""")
    applied, after = _run([seed_and_rewire, _reset])
    assert applied["inlineLeft"] == "60px", f"the seeded position must actually be applied first (got {applied})"
    assert abs(after["centreOffset"]) <= 2 and after["fromBottom"] == 8, f"not home: {after}"
    assert after["stored"] is None


def test_reset_with_no_drag_is_a_quiet_noop(playwright_available):
    """An orb never dragged is already home — reset must not move it or throw."""
    before, after = _run([_noop, _reset])
    assert abs(after["centreOffset"]) <= 2 and after["fromBottom"] == 8
    assert not after["errors"], f"page errors: {after['errors']}"


def test_home_is_the_centre_of_the_desk_not_the_window(playwright_available):
    """With a chat column docked, «posición inicial» means the centre of the SHRUNK desk — the visible area."""
    async def drag_then_dock(pg):
        await _drag_orb(pg, -320, 0)
        await pg.evaluate("""() => document.documentElement.style.setProperty("--chatdock-l", "600px")""")
    dropped, after = _run([drag_then_dock, _reset])
    assert abs(after["centreOffset"]) <= 2, f"after reset the orb centres on the desk, not the window: {after}"


def test_the_reset_reaches_the_orb():
    """The wiring between the two owners, as a source contract: `_clearCanvasAndLog()` (the client-side
    deterministic reset path — both resetHard and resetFull go through it) announces `hb:canvas-reset`,
    and Orb.js answers it with resetDraggable on `hb_pos_orb`. The mechanics are proven rendered above;
    this pins that the rendered thing is what the Reset button actually triggers."""
    lk = SESSION_LK.read_text(encoding="utf-8")
    start = lk.index("function _clearCanvasAndLog")
    body = lk[start:lk.index("\n}", start)]
    assert 'new CustomEvent("hb:canvas-reset")' in body, \
        "_clearCanvasAndLog must announce hb:canvas-reset — it is the path every Reset goes through"
    orb = ORB.read_text(encoding="utf-8")
    li = orb.index('addEventListener("hb:canvas-reset"')
    listener = orb[li:orb.index("});", li)]
    assert 'resetDraggable(wrapEl, "hb_pos_orb")' in listener, \
        "Orb.js must answer hb:canvas-reset by sending the orb home via resetDraggable"
