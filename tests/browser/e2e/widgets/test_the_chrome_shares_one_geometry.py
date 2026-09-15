"""The desktop's own chrome shares ONE geometry, and each of its states is said twice (V2-690).

The operator's second pass over the design system, verbatim in spirit: the window separates from the desk but
not enough; the title bar «demasiado discreto»; the system tray in the top-right reads as loose buttons that
happen to be near each other rather than as one thing («agruparlos visualmente mejor… todos deben compartir
dimensiones, padding, border radius, hover»); the bottom bar must say which application is ACTIVE; and the
chat bubbles must share one radius, one padding, one max-width and one type size, with the purple an accent
rather than the loudest surface on the screen.

RENDERED, every case, against the REAL shell — this is chrome that exists only once the browser has resolved
the cascade across four stylesheets (palette.css, components.css, styles.css and the sheet desktop.js injects)
plus a live canvas. A source grep can see a declaration; it cannot see that two controls ended up the same
height, that exactly one chip is marked, or that the accent a bubble resolves to is not the accent token.

ONE case here is deliberately a GEOMETRY check and not a pixel one, and says so where it stands: the dock's
active-application marker. Pillow is not a declared dependency of this repo, and a test that reaches for an
undeclared import is a test that silently skips (a fault this codebase has paid for by name). The rule it
encodes is the one that was actually broken while this was written — a marker hung below a clipping box.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time

import pytest

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
W, H = 1440, 900

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

#: Two plain cards, so the canvas has both a FOCUSED window and a resting one to compare it against.
DATA = {"agenda": {"title": "Agenda"}, "musica": {"title": "Musica"}}
WIDGET_JS = ('export function render(el, data){ el.style.minHeight = "240px";'
             ' el.textContent = "W:" + ((data && data.title) || "?"); }')
ROUTE_RE = re.compile(
    r"^https?://[^/]+/(widgets(/.*)?|api/(canvas/.*|desktop/epoch|client-log|run|status|ui-event))(\?.*)?$")


def _route(r):
    path = re.sub(r"^https?://[^/]+", "", r.request.url).split("?", 1)[0]

    def j(obj):
        r.fulfill(status=200, content_type="application/json", body=json.dumps(obj))

    if path == "/widgets":
        return j({"widgets": [{"id": w, "size": {"w": 420, "h": 320}} for w in DATA]})
    if path == "/widgets/registry":
        return j({"registry": []})
    if path == "/api/desktop/epoch":
        return j({"epoch": ""})
    if path == "/api/canvas/layout":
        return j({"items": [], "live": []})
    if path in ("/api/canvas/state", "/api/client-log", "/api/ui-event"):
        return j({"ok": True})
    if path == "/api/run":
        return j({"state": "running", "running": True})
    m = re.match(r"^/widgets/([^/]+)/(data|manifest|widget\.js)$", path)
    if m:
        wid, kind = m.group(1), m.group(2)
        if kind == "widget.js":
            return r.fulfill(status=200, content_type="application/javascript", body=WIDGET_JS)
        if kind == "manifest":
            return j({"id": wid})
        return j(DATA.get(wid, {"title": wid}))
    return r.fallback()


_CHROME = """() => {
  const cs = el => getComputedStyle(el);
  const h = el => Math.round(el.getBoundingClientRect().height);
  const wins = [...document.querySelectorAll('.hb-win')];
  const focused = wins.find(c => c.classList.contains('hb-focus'));
  const resting = wins.find(c => !c.classList.contains('hb-focus'));
  const head = focused.querySelector('.hb-head');
  const x = focused.querySelector('.hb-x');
  const chips = [...document.querySelectorAll('#wrail .wr-chip')];
  const on = chips.find(c => c.classList.contains('on'));
  const bar = on ? getComputedStyle(on, '::after') : null;
  const ics = [...document.querySelectorAll('.tr .ic')];
  const reset = document.querySelector('.tr .reset');
  const tr = document.querySelector('.tr');
  const root = getComputedStyle(document.documentElement);
  return {
    winRestShadow: cs(resting).boxShadow, winRestBorder: cs(resting).borderTopColor,
    winFocusShadow: cs(focused).boxShadow, winFocusBorder: cs(focused).borderTopColor,
    headH: h(head), ctlH: h(x), ctlW: Math.round(x.getBoundingClientRect().width),
    ctlInk: cs(x).color, ctlFontSize: cs(x).fontSize,
    chips: chips.map(c => ({label: c.textContent, on: c.classList.contains('on')})),
    focusedWid: focused.dataset.wid,
    chipOverflow: on ? cs(on).overflow : null,
    chipMarkBottom: bar ? bar.bottom : null,
    chipMarkHeight: bar ? bar.height : null,
    chipMarkBg: bar ? bar.backgroundColor : null,
    chipBg: on ? cs(on).backgroundColor : null,
    railH: h(document.querySelector('#wrail')),
    railTokenH: root.getPropertyValue('--wrail-h').trim(),
    railToolH: (() => { const b = document.querySelector('#wrail .wr-tools button'); return b ? h(b) : null; })(),
    chipH: on ? h(on) : null,
    chipWeightOn: on ? cs(on).fontWeight : null,
    chipWeightRest: (() => { const c = chips.find(x => !x.classList.contains('on'));
                             return c ? cs(c).fontWeight : null; })(),
    // How close the PAINTED label gets to the chip's own edge. It is measured with the label FORCED to
    // overflow, because that is the only state in which the answer means anything: a short name is centred
    // and leaves slack on both sides whether or not the box has padding at all — a first version of this
    // read a comfortable gap off a centred "Agenda" and stayed green with the padding deleted. Overflowing,
    // the label fills the content box exactly, so the gap IS the padding. Restored immediately; this page is
    // the harness's own throwaway render.
    chipInkGap: (() => { if (!on) return null; const n = on.querySelector('.wr-chipn'); if (!n) return null;
      const keep = n.textContent; n.textContent = 'M'.repeat(60);
      const a = n.getBoundingClientRect(), b = on.getBoundingClientRect();
      const gap = Math.round(Math.min(a.left - b.left, b.right - a.right));
      n.textContent = keep; return gap; })(),
    chipRestBg: chips.filter(c => !c.classList.contains('on')).map(c => cs(c).backgroundColor)[0] || null,
    trBorder: cs(tr).borderTopColor, trShadow: cs(tr).boxShadow,
    trayHeights: ics.map(h).concat(reset ? [h(reset)] : []),
    trayRadii: ics.map(e => cs(e).borderTopLeftRadius).concat(reset ? [cs(reset).borderTopLeftRadius] : []),
    trayOwnFrames: ics.map(e => cs(e).borderTopColor),
    muted2: root.getPropertyValue('--hb-muted-2').trim(),
    widgetBg: root.getPropertyValue('--hb-bg').trim(),
    accent: root.getPropertyValue('--hb-accent').trim(),
  };
}"""

#: Four bubbles appended to the REAL transcript element, so they inherit the real cascade rather than a
#: fixture's copy of it (the V2-608 lesson: a harness whose DOM differs measures a different product).
_BUBBLES = """() => {
  const list = document.querySelector('.cw-list');
  const mk = (cls) => { const d = document.createElement('div'); d.className = 'cw-msg ' + cls;
                        d.textContent = 'x'.repeat(40); list.appendChild(d); return d; };
  const read = k => { const c = getComputedStyle(mk(k));
                      return {k, radius: c.borderTopLeftRadius, padding: c.padding,
                              maxWidth: c.maxWidth, fontSize: c.fontSize, bg: c.backgroundColor}; };
  const kinds = ['you', 'agent', 'peer', 'sys'].map(read);
  const root = getComputedStyle(document.documentElement);
  const scale = [1,2,3,4,5,6].map(n => root.getPropertyValue('--sp-' + n).trim());
  return {kinds, gap: getComputedStyle(list).rowGap, scale};
}"""


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _srgb(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _contrast(a: str, b: str) -> float:
    def lum(hexs):
        hexs = hexs.lstrip("#")
        r, g, bl = (int(hexs[i:i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * _srgb(r) + 0.7152 * _srgb(g) + 0.0722 * _srgb(bl)
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


@pytest.fixture(scope="module")
def measured():
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-c", PREVIEW % (ENGINE, os.path.join(ENGINE, "frontend"), port)],
                            cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            break
        except OSError:
            time.sleep(0.5)
    else:  # pragma: no cover
        proc.terminate()
        pytest.skip("preview server never came up")
    time.sleep(1.0)
    out = {"errors": []}
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = b.new_context(viewport={"width": W, "height": H}).new_page()
            pg.on("pageerror", lambda e: out["errors"].append(str(e)))
            pg.route(ROUTE_RE, _route)
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            pg.wait_for_timeout(2200)
            pg.evaluate("() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil')"
                        ".forEach(e => e.remove())")
            # musica first, agenda second: the LAST one shown is the one the operator is in, which is the
            # fact the dock has to report. Opening them in this order is what makes the check non-vacuous.
            pg.evaluate("() => window.zaelar.show('musica')")
            pg.wait_for_timeout(400)
            pg.evaluate("() => window.zaelar.show('agenda')")
            pg.wait_for_timeout(700)
            out["chrome"] = pg.evaluate(_CHROME)
            pg.evaluate("() => window.zaelar.panel('chat')")
            pg.wait_for_timeout(400)
            out["bubbles"] = pg.evaluate(_BUBBLES)
            b.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()
    return out


def test_the_desk_shows_through_a_crisp_window_edge(measured):
    """«Aumentar MUY ligeramente el contraste del borde exterior. Añadir una sombra exterior extremadamente
    sutil.» One dark pixel with no blur, carried as the first layer of the window shadow, is what makes the
    boundary crisp; a bigger blur would only make the card float, which this pass exists to avoid."""
    m = measured["chrome"]
    assert "0px 0px 0px 1px" in m["winRestShadow"], \
        f"a resting window needs its outer hairline ring: {m['winRestShadow']}"
    assert "blur" not in m["winRestShadow"]


def test_focus_is_a_degree_of_the_same_window_and_not_a_different_one(measured):
    """«No cambiar drásticamente colores ni añadir efectos llamativos.» Both signals move a notch — border AND
    shadow — so the card being worked in is findable without any card becoming a different design."""
    m = measured["chrome"]
    assert m["winFocusBorder"] != m["winRestBorder"], m["winFocusBorder"]
    assert m["winFocusShadow"] != m["winRestShadow"]


def test_the_title_bar_is_a_real_window_bar_with_reachable_controls(measured):
    """«altura consistente ~36-40px… controles de ventana con hit-area mínimo 28-32px… iconos pequeños, pero
    no casi invisibles.» The ink matters as much as the box: these were painted in the secondary step while it
    still measured 4.2:1, inside a 28px target."""
    m = measured["chrome"]
    assert 36 <= m["headH"] <= 40, f"the title bar is outside the stated band: {m['headH']}"
    assert m["ctlH"] >= 30 and m["ctlW"] >= 30, f"window controls need a >=30px hit area: {m}"
    assert m["ctlFontSize"] == "14px", m["ctlFontSize"]


def test_the_dock_names_the_ACTIVE_application(measured):
    """«active app/state claramente definido… revisar especialmente el elemento AGENDA.» The bar could say
    what was OPEN and what was HIDDEN and had no way to say which card the operator is IN. It reads that from
    the canvas's own `hb-focus` marker, so the dock and the window border cannot disagree about it."""
    m = measured["chrome"]
    marked = [c for c in m["chips"] if c["on"]]
    assert len(marked) == 1, f"exactly one application is active: {m['chips']}"
    assert marked[0]["label"].upper().startswith("AGEND"), \
        f"the marked chip must be the focused card ({m['focusedWid']}): {m['chips']}"
    assert m["chipBg"] != m["chipRestBg"], "an active chip that looks like every other chip says nothing"


def test_the_active_chip_marker_lands_INSIDE_the_chip_that_clips_it(measured):
    """Said twice — an accent wash AND an accent bar — because a state carried by colour alone is a state a
    colourblind reader does not get.

    This is a GEOMETRY check, not a pixel one (Pillow is not a dependency of this repo, and an undeclared
    import is how a test silently stops running). It encodes the rule that was actually broken while this was
    written: every button in the bar is `overflow:hidden`, which clips at the PADDING box, so a marker at
    `bottom:-1px` renders at half the weight it declares — a defect no computed-style read can see, because
    the declaration stays perfect.
    """
    m = measured["chrome"]
    assert m["chipMarkHeight"] == "2px" and "rgb" in (m["chipMarkBg"] or ""), \
        f"there is no marker to place: {m['chipMarkHeight']} / {m['chipMarkBg']}"
    if m["chipOverflow"] not in ("visible", None):
        bottom = m["chipMarkBottom"]
        assert bottom and not bottom.lstrip().startswith("-"), \
            f"a clipping chip ({m['chipOverflow']}) renders only what is inside it: bottom={bottom}"


def test_a_dock_chip_is_a_LABEL_and_not_an_icon_square(measured):
    """V2-692, the operator reading his own screenshot: «no sé si deberíamos reducir un 10% la altura de esta
    barra, la veo como muy grande… fíjate que no hay padding lateral, el botón es muy alto, cosa que no tiene
    sentido, parece un desperdicio de espacio».

    All three of his complaints came from ONE inheritance: the chips are `#wrail button`, so they took the
    44px square and the `padding:0` that an ICON wants, and then wore a word inside it. Measured before the
    change: 31px of dead air inside a 44px box, and 4px of slack around a 56px run of letters. The rules that
    replace it are checked on what is PAINTED, not on the declarations — a later rule can zero a padding
    without removing it.
    """
    m = measured["chrome"]
    assert m["railTokenH"] and m["railH"] <= 58, \
        f"the band is chrome: every px it takes is a px the desk loses (h={m['railH']}, token={m['railTokenH']})"
    assert m["chipH"] and m["railToolH"] and m["chipH"] < m["railToolH"], \
        f"a chip holds a word, an icon button holds a glyph — they cannot be the same box: {m['chipH']} vs {m['railToolH']}"
    assert m["chipInkGap"] is not None and m["chipInkGap"] >= 8, \
        f"the label runs into the chip's own edge: {m['chipInkGap']}px of side room"
    # The active state is said a third time in WEIGHT, which is the half a reader who cannot separate the
    # accent from the ground still receives.
    assert int(m["chipWeightOn"]) > int(m["chipWeightRest"]), \
        f"active is carried by colour alone: {m['chipWeightOn']} vs {m['chipWeightRest']}"


def test_the_system_tray_is_ONE_group_whose_members_share_a_geometry(measured):
    """«Los controles de la esquina superior derecha pertenecen al desktop/system layer. Agruparlos
    visualmente mejor. Todos deben compartir dimensiones, padding, border radius, hover, active state.»
    Reset was a pill of a different height and radius entirely; the frame now belongs to the GROUP, which is
    what lets its members stop carrying frames of their own."""
    m = measured["chrome"]
    assert m["trBorder"] != "rgba(0, 0, 0, 0)" and m["trShadow"] not in ("none", None), \
        f"the tray has to read as one object: border={m['trBorder']} shadow={m['trShadow']}"
    assert len(set(m["trayHeights"])) == 1, f"one height for every tray control: {m['trayHeights']}"
    assert len(set(m["trayRadii"])) == 1, f"one radius for every tray control: {m['trayRadii']}"
    assert all(c == "rgba(0, 0, 0, 0)" for c in m["trayOwnFrames"]), \
        f"the group is framed, not its members: {m['trayOwnFrames']}"


def test_every_conversational_bubble_shares_one_geometry(measured):
    """«border-radius común, padding común, max-width común, typography consistente, separación vertical
    regular.» The system line stays deliberately smaller and wider — it is a note ABOUT the conversation, not
    a turn in it — so the three that are turns are what must agree."""
    b = measured["bubbles"]
    turns = [k for k in b["kinds"] if k["k"] != "sys"]
    for prop in ("radius", "padding", "maxWidth", "fontSize"):
        assert len({k[prop] for k in turns}) == 1, \
            f"{prop} differs between bubbles: {[(k['k'], k[prop]) for k in turns]}"
    # Read FROM the scale rather than pinned to a number: the claim is that the rhythm is a STEP of the
    # scale (V2-691 moved it 12 -> 16 for reading comfort and the old literal caught that as a failure,
    # which is the assertion measuring the wrong thing). The 12px floor is the operator's own rule.
    assert b["gap"] in b["scale"], f"the vertical rhythm must be a step of --sp-*: {b['gap']} not in {b['scale']}"
    assert float(b["gap"].rstrip("px")) >= 12, f"messages need room to separate: {b['gap']}"


def test_the_operators_bubble_is_an_accent_and_not_the_accent(measured):
    """«El purple debe ser accent, no dominar toda la aplicación. Si es necesario, reducir ligeramente
    saturación/luminosidad del bubble purple.» A column of pure-accent boxes makes the accent the loudest
    thing on screen, and an accent that is everywhere has stopped meaning «interactive»."""
    m, b = measured["chrome"], measured["bubbles"]
    you = next(k for k in b["kinds"] if k["k"] == "you")
    accent = m["accent"].lstrip("#")
    pure = "rgb(%d, %d, %d)" % tuple(int(accent[i:i + 2], 16) for i in (0, 2, 4))
    assert you["bg"] != pure, f"the bubble is still the raw accent: {you['bg']}"


def test_secondary_ink_clears_the_contrast_floor_on_the_widget_ground(measured):
    """«Aumentar ligeramente legibilidad de secondary text… especial atención a iconos grises pequeños:
    algunos están demasiado cerca del límite de visibilidad.» Measured rather than judged: this is the token
    the small grey icons and every metadata line are painted with, and it sat under 4.5:1."""
    m = measured["chrome"]
    ratio = _contrast(m["muted2"], m["widgetBg"])
    assert ratio >= 4.5, f"{m['muted2']} on {m['widgetBg']} is {ratio:.2f}:1"


def test_the_shell_boots_without_a_page_error(measured):
    """Everything above measures a page that came up; this says so out loud, because a chrome test that runs
    against a half-dead shell measures the fallbacks (V2-559's class: the module dies and nothing says it)."""
    assert not measured["errors"], "; ".join(measured["errors"][:3])
