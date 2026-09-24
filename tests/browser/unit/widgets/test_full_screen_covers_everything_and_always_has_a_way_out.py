"""V2-759 — a full-screen card covers EVERYTHING, and there is always a way back. Rendered, not grepped.

The operator, 2026-09-24, with a screenshot of the image viewer «at full screen» next to his docked chat:

    «yo entiendo que un widget pase a pantalla completa, es decir, que se ponga por encima de absolutamente
    todo y siempre de sistema con alguna especie de iconito para cerrarlo, arriba del todo a la derecha, por
    ejemplo, una pequeña X que no se vea mucho pero que al poner el ratón encima de toda esa zona […] sí que
    me permita clicar o hacer doble clic en la pantalla y que todo vuelva a la visión normal […] Para que la
    gente no se quede sin poder ver la barra, sin poder actuar con las cosas.»

WHY IT HAS TO BE RENDERED, IN THE PRODUCT'S DOM. `#desk` carries `transform: translate3d(0,0,0)` (V2-608),
which makes it the containing block for every `position:fixed` descendant AND a stacking context. So the
card's `position:fixed; left:0; width:100vw` was measured from the desk — which starts at the docked chat's
right edge — and no z-index on the card could ever lift it above the chat, which lives outside `#desk`. The
CSS read correctly and the screen was wrong. The existing canvas harness mounts the stage loose in <body>,
where fixed resolves against the window and the bug cannot exist: V2-608 already wrote down that «a harness
whose DOM differs from the product's measures a different product». This one builds the real shape and
loads the real stylesheet, and every assertion is a POINT on the screen: who is on top there.
"""
from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time

import pytest

from tests.waiting import until_sync

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]

VW, VH = 1400, 900
CHAT_W = 320

# The body of a card: a text line, a row that OWNS its double click (how archivos/musica wire theirs), an
# input, and — for the embedded-player case — an iframe covering the rest, which swallows pointer events.
_STUB_WIDGET = """export function render(el){
  el.innerHTML = '<div class="plain" style="height:120px">contenido</div>'
    + '<div class="own" style="height:40px">fila con doble clic propio</div>'
    + '<input class="field" value="texto">'
    + '<iframe class="player" style="width:100%;height:400px;border:0" srcdoc="<body style=background:#123></body>"></iframe>';
  el.querySelector('.own').ondblclick = () => { window.__ownDbl = (window.__ownDbl||0) + 1; };
}
export default { render };
"""
_REGISTRY = {"widgets": [{"id": "visor", "name": "Visor", "fullscreen": "native"},
                         {"id": "hoja", "name": "Hoja"}]}



def _listening(port: int) -> bool:
    import socket as _s
    try:
        _s.create_connection(("127.0.0.1", port), 0.2).close()
        return True
    except OSError:
        return False

def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def page():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            pg = browser.new_page(viewport={"width": VW, "height": VH})
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))

            def _json(route, payload):
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

            pg.route("**/widgets", lambda r: _json(r, _REGISTRY))
            pg.route("**/widgets/registry", lambda r: _json(r, {"registry": []}))
            pg.route("**/widgets/*/widget.js", lambda r: r.fulfill(
                status=200, content_type="application/javascript", body=_STUB_WIDGET))
            pg.route("**/widgets/*/data*", lambda r: _json(r, {}))
            pg.route("**/widgets/*/aliases*", lambda r: _json(r, {"ok": True, "aliases": []}))
            pg.route("**/api/**", lambda r: _json(r, {}))

            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            # THE PRODUCT'S SHAPE (frontend/app/main.js + core/system-surfaces.js): the stage and the rail live
            # INSIDE #desk; the chat lives OUTSIDE it, at body level, docked left with its column reserved.
            pg.evaluate("""async ([port, chatW]) => {
                const css = document.createElement('link'); css.rel = 'stylesheet';
                css.href = `http://127.0.0.1:${port}/frontend/app/styles.css`;
                document.head.append(css);
                await new Promise(r => { css.onload = r; css.onerror = r; });
                document.documentElement.style.setProperty('--chatdock-l', chatW + 'px');
                document.documentElement.style.setProperty('--banner-h', '0px');   // set by JS in the product
                // THE VOICE ROAD, pinned. A voice order arrives with NO user activation, so the desktop takes the
                // in-app road (V2-583). Left alone, a real click from the previous test keeps activation alive for
                // a few seconds and the next call silently takes the NATIVE road instead — measured while
                // writing this file, and it made the exits look broken. The native road has its own test below.
                window.__voiceRoad = true;
                Object.defineProperty(navigator, 'userActivation',
                    {configurable: true, get: () => ({isActive: !window.__voiceRoad, hasBeenActive: true})});
                document.body.innerHTML =
                    '<div id="desk"><div class="canvas"></div><div class="wstage" id="wstage"></div>'
                  + '<div id="wrail" style="position:fixed;left:0;right:0;bottom:0;height:58px;z-index:9002;'
                  + 'display:block;background:#333">barra</div></div>'
                  + `<div class="chatwall docked dock-left" style="display:block;width:${chatW}px">chat</div>`
                  + '<div id="activity"></div>';
                document.body.classList.add('chatdock-l');
                const m = await import(`http://127.0.0.1:${port}/frontend/app/widgets/desktop.js?v=1`);
                window.__desk = new m.Desktop(document.getElementById('wstage'));
            }""", [port, CHAT_W])
            assert not errors, f"the canvas threw before a card was asked for: {errors}"
            pg._hb_errors = errors
            yield pg
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)


def _open(pg, wid):
    pg.evaluate("(id) => window.__desk.show(id, {data: {ok: true}})", wid)
    pg.wait_for_selector(f"[data-wid='{wid}'] .plain", timeout=5000)
    pg.wait_for_timeout(150)


def _geom(pg, wid):
    return pg.evaluate("""(id) => { const c = document.querySelector(`[data-wid='${id}']`);
        const r = c.getBoundingClientRect();
        return {left: c.style.left, top: c.style.top, w: c.style.width, h: c.style.height,
                x: Math.round(r.x), y: Math.round(r.y), rw: Math.round(r.width), rh: Math.round(r.height),
                cls: c.className, min: c.classList.contains('hb-minned')}; }""", wid)


def _owner(pg, x, y):
    """WHO is on top at that point: the card's id, 'chat', 'rail', or the tag of whatever else."""
    return pg.evaluate("""([x, y]) => { const e = document.elementFromPoint(x, y); if (!e) return null;
        const card = e.closest('.hb-win'); if (card) return 'card:' + card.dataset.wid
            + (e.closest('.hb-cinexit') ? ':exit' : '') + (e.closest('.hb-head') ? ':head' : '')
            + (e.tagName === 'IFRAME' ? ':iframe' : '');
        if (e.closest('.chatwall')) return 'chat'; if (e.closest('#wrail')) return 'rail';
        return e.tagName.toLowerCase(); }""", [x, y])


def _full(pg, wid, on=True):
    pg.evaluate("([id, on]) => window.__desk.fullscreen(id, on)", [wid, on])
    # The card plays a short scale animation («boop») when it comes to the front; a rectangle read mid-flight
    # is off by a few pixels in every direction. Wait for the animation, not for a guessed number of ms.
    pg.wait_for_function("(id) => { const c = document.querySelector(`[data-wid='${id}']`);"
                         " return c && !c.classList.contains('boop')"
                         "   && !c.getAnimations().some(a => a.playState === 'running'); }", arg=wid, timeout=3000)


def _is_full(pg, wid):
    """Either road — the same question `Desktop._isFull` asks."""
    return pg.evaluate("(id) => { const c = document.querySelector(`[data-wid='${id}']`);"
                       " return document.fullscreenElement === c"
                       "   || c.classList.contains('hb-cinema') || c.classList.contains('hb-fullwide'); }", wid)


def _chat_point(pg):
    """The middle of the docked chat column, measured — never assumed from a constant."""
    r = pg.evaluate("() => { const r = document.querySelector('.chatwall').getBoundingClientRect();"
                    " return [Math.round(r.x + r.width / 2), Math.round(r.y + r.height / 2)]; }")
    return tuple(r)


# ── A · IT COVERS EVERYTHING ─────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("wid", ["visor", "hoja"])
def test_full_screen_covers_the_docked_chat_and_the_rail(page, wid):
    """His screenshot, measured: the chat column and the bottom band must be the CARD's, not the chat's."""
    _open(page, wid)
    cx, cy = _chat_point(page)
    assert _owner(page, cx, cy) == "chat", "precondition: the docked chat is on screen"
    _full(page, wid, True)
    at_chat = _owner(page, cx, cy)
    at_rail = _owner(page, VW // 2, VH - 20)
    g = _geom(page, wid)
    _full(page, wid, False)
    assert at_chat.startswith(f"card:{wid}"), \
        f"the docked chat is still on top of a full-screen «{wid}» ({at_chat}) — #desk is still the containing block"
    assert at_rail.startswith(f"card:{wid}"), f"the bottom band still belongs to «{at_rail}», not to the card"
    assert (g["x"], g["y"], g["rw"], g["rh"]) == (0, 0, VW, VH), f"«{wid}» does not cover the screen: {g}"


def test_coming_back_gives_the_chat_its_place_again(page):
    _open(page, "visor")
    _full(page, "visor", True)
    _full(page, "visor", False)
    assert _owner(page, *_chat_point(page)) == "chat", "leaving full screen did not give the chat back"


# ── B · THE WAY BACK: the corner X, a double click, Escape — each restoring the exact geometry ───────────────
def _roundtrip(pg, wid, leave):
    _open(pg, wid)
    before = _geom(pg, wid)
    _full(pg, wid, True)
    assert _is_full(pg, wid)
    leave()
    pg.wait_for_timeout(150)
    after = _geom(pg, wid)
    return before, after


def _same_place(before, after):
    return (before["left"], before["top"], before["w"], before["h"]) == \
           (after["left"], after["top"], after["w"], after["h"]) and not after["min"] \
        and "hb-cinema" not in after["cls"] and "hb-fullwide" not in after["cls"]


@pytest.mark.parametrize("wid", ["visor", "hoja"])
def test_the_corner_x_brings_it_back_exactly_where_it_was(page, wid):
    before, after = _roundtrip(page, wid, lambda: page.mouse.click(VW - 12, 12))
    assert _same_place(before, after), f"the X did not restore «{wid}»: {before} → {after}"


@pytest.mark.parametrize("wid", ["visor", "hoja"])
def test_the_corner_x_owns_a_LARGE_zone_not_just_its_glyph(page, wid):
    """«al poner el ratón encima de toda esa zona, de una zona grande… sí que me permita clicar»."""
    _open(page, wid)
    _full(page, wid, True)
    hits = {p: _owner(page, *p) for p in [(VW - 4, 4), (VW - 45, 6), (VW - 6, 45), (VW - 40, 40)]}
    _full(page, wid, False)
    bad = {p: h for p, h in hits.items() if not h.endswith(":exit")}
    assert not bad, f"parts of the corner are not the exit: {bad}"


def test_in_fullwide_the_cards_own_close_is_not_under_the_exit(page):
    """The header stays in fullwide (V2-693), and its ✕ CLOSES the card — it must not sit in the exit's
    corner, where a click meant for «leave full screen» would throw the whole widget away."""
    _open(page, "hoja")
    _full(page, "hoja", True)
    close = page.evaluate("""() => { const b = document.querySelector("[data-wid='hoja'] .hb-x");
        const r = b.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height}; }""")
    _full(page, "hoja", False)
    assert close["x"] + close["w"] <= VW - 52, f"the card's close button is under the exit corner: {close}"


@pytest.mark.parametrize("wid", ["visor", "hoja"])
def test_a_double_click_anywhere_brings_it_back(page, wid):
    def leave():
        box = page.evaluate(f"() => {{ const r = document.querySelector(\"[data-wid='{wid}'] .plain\")"
                            f".getBoundingClientRect(); return [r.x + 20, r.y + 20]; }}")
        page.mouse.dblclick(*box)
    before, after = _roundtrip(page, wid, leave)
    assert _same_place(before, after), f"a double click did not restore «{wid}»: {before} → {after}"


def test_a_double_click_the_widget_OWNS_is_left_to_the_widget(page):
    """archivos opens a file and musica plays a row on double click; exiting on top of that would be two
    things for one gesture."""
    _open(page, "hoja")
    _full(page, "hoja", True)
    page.evaluate("() => { window.__ownDbl = 0; }")
    box = page.evaluate("() => { const r = document.querySelector(\"[data-wid='hoja'] .own\")"
                        ".getBoundingClientRect(); return [r.x + 10, r.y + 10]; }")
    page.mouse.dblclick(*box)
    page.wait_for_timeout(120)
    still = _is_full(page, "hoja")
    own = page.evaluate("() => window.__ownDbl")
    _full(page, "hoja", False)
    assert own >= 1, "the widget's own double click did not run"
    assert still, "a double click the widget handles itself ALSO threw the card out of full screen"


def test_a_double_click_in_a_field_selects_a_word_and_nothing_else(page):
    _open(page, "hoja")
    _full(page, "hoja", True)
    box = page.evaluate("() => { const r = document.querySelector(\"[data-wid='hoja'] .field\")"
                        ".getBoundingClientRect(); return [r.x + 10, r.y + 5]; }")
    page.mouse.dblclick(*box)
    page.wait_for_timeout(120)
    still = _is_full(page, "hoja")
    _full(page, "hoja", False)
    assert still, "a double click inside a text field left full screen"


@pytest.mark.parametrize("wid", ["visor", "hoja"])
def test_escape_brings_it_back(page, wid):
    before, after = _roundtrip(page, wid, lambda: page.keyboard.press("Escape"))
    assert _same_place(before, after), f"Escape did not restore «{wid}»: {before} → {after}"


def test_over_an_embedded_player_the_corner_is_still_OURS(page):
    """An iframe swallows clicks and double clicks — over a video, the corner is the exit that always works.
    The player fills the card here, and the corner must still answer to the desktop, not to the iframe."""
    _open(page, "visor")
    _full(page, "visor", True)
    page.evaluate("""() => { const f = document.querySelector("[data-wid='visor'] .player");
        f.style.position = 'fixed'; f.style.inset = '0'; f.style.height = '100vh'; f.style.zIndex = '5'; }""")
    corner = _owner(page, VW - 10, 10)
    middle = _owner(page, VW // 2, VH // 2)
    page.evaluate("""() => { const f = document.querySelector("[data-wid='visor'] .player");
        f.style.position = ''; f.style.inset = ''; f.style.height = '400px'; f.style.zIndex = ''; }""")
    _full(page, "visor", False)
    assert middle.endswith(":iframe"), f"precondition: the player covers the middle ({middle})"
    assert corner.endswith(":exit"), f"over a full-bleed player the corner belongs to «{corner}», not the exit"


# ── C · ENTERING AND LEAVING ARE TWO OPERATIONS, NOT ONE TOGGLE ──────────────────────────────────────────────
def test_asking_twice_for_full_screen_does_not_take_it_back_out(page):
    """With the toggle, «ponlo en pantalla completa» said twice LEFT full screen."""
    _open(page, "hoja")
    _full(page, "hoja", True)
    _full(page, "hoja", True)
    still = _is_full(page, "hoja")
    _full(page, "hoja", False)
    assert still, "a second «on» toggled the card back out"


def test_leaving_a_card_that_is_not_full_screen_touches_nothing(page):
    """«No, sigues estando en pantalla completa» on a NORMAL card used to blow it up (toggle), and `minimize`
    sends a normal card to the rail. The exit is neither."""
    _open(page, "hoja")
    before = _geom(page, "hoja")
    _full(page, "hoja", False)
    after = _geom(page, "hoja")
    assert _same_place(before, after), f"leaving on a normal card moved it: {before} → {after}"


def test_leaving_needs_no_name(page):
    """«Sal de pantalla completa» names no card (V2-609): an empty id is «the one that covers the screen»."""
    _open(page, "visor")
    before = _geom(page, "visor")
    _full(page, "visor", True)
    page.evaluate("() => window.__desk.fullscreen('', false)")
    page.wait_for_timeout(150)
    assert _same_place(before, _geom(page, "visor")), "an unnamed exit did not find the full-screen card"


def test_the_old_toggle_still_means_what_it_meant(page):
    """Every caller that has not been told about `on` keeps its behaviour — the header's double click, the
    ⤢ button, an older event with no direction."""
    _open(page, "hoja")
    page.evaluate("() => window.__desk.fullscreen('hoja')")
    page.wait_for_timeout(120)
    entered = _is_full(page, "hoja")
    page.evaluate("() => window.__desk.fullscreen('hoja')")
    page.wait_for_timeout(120)
    assert entered and not _is_full(page, "hoja"), "the undirected call is no longer a toggle"


def test_the_NATIVE_road_also_leaves_by_double_click(page):
    """A gesture (the ⤢ button, a click) takes the browser's own full screen for the video. Double click has
    to bring it back there too — Escape the browser already handles."""
    _open(page, "visor")
    page.evaluate("() => { window.__voiceRoad = false; }")
    try:
        page.mouse.click(VW - 5, VH - 5)          # a real gesture, so the browser grants activation
        page.evaluate("() => window.__desk.fullscreen('visor', true)")
        page.wait_for_function("() => !!document.fullscreenElement", timeout=3000)
        box = page.evaluate("() => { const r = document.querySelector(\"[data-wid='visor'] .plain\")"
                            ".getBoundingClientRect(); return [r.x + 20, r.y + 20]; }")
        page.mouse.dblclick(*box)
        page.wait_for_function("() => !document.fullscreenElement", timeout=3000)
    finally:
        page.evaluate("() => { window.__voiceRoad = true; if (document.fullscreenElement) document.exitFullscreen(); }")
    assert not _is_full(page, "visor")


def test_nothing_threw(page):
    assert not page._hb_errors, f"the canvas threw during the full-screen round trips: {page._hb_errors}"
