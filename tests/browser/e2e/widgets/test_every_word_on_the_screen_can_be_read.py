"""Every word on the screen clears a contrast floor and a size floor — MEASURED, never judged (V2-691).

The operator's third pass, and the rule he left standing for everything after it: *«cuando haya conflicto
entre estética minimalista y facilidad de lectura, priorizar facilidad de lectura»*. He named the symptoms —
«lila sobre negro», «gris medio sobre negro», «labels pequeñas sobre fondos oscuros» — and the reader:
somebody 45-60 working several hours in this UI.

WHY THIS IS A RENDER TEST AND NOT A LINT. A token's declared value says nothing about the ratio a glyph
actually achieves: the ground under it is whatever the cascade composited there — a translucent wash over a
card over a panel over the desk — and `opacity` on any ancestor dims the ink against it. Both of those are
facts about the compositor, so the compositor is what gets asked. The walker below pushes every ancestor's
background onto a stack, composites them bottom-up, folds the inherited opacity chain into the ink, and only
then computes WCAG's own ratio. Nothing here is a matter of taste; every number has a derivation.

THE TWO FLOORS, in the operator's own words:
  · contrast — WCAG AA: 4.5:1 for body text, 3:1 for large text (>=24px, or >=18.66px at weight 700).
  · size — «metadata pequeña: no bajar de 12px». UI text should be 13px, which this does NOT assert:
    12.75px (the --fs-micro step at a 17px root) is legal metadata and is where most of the shell bottoms
    out, so a 13px assertion would fail on text that is correctly metadata. The floor that is enforced is
    the one that has a single unambiguous answer.

⚠️ THE INSTRUMENT LIED FIRST, and that is why the colour parser is written out longhand below rather than as
one regex. A `color-mix()` resolves to `color(srgb 0.54 0.44 0.89)` — components 0..1, not 0..255 — and an
rgb() parser reads that lilac as near-black and reports a 1.06:1 failure on a bubble that is perfectly
legible. The first run of this audit "found" exactly that, on the one surface the operator had complained
about, which is the most convincing way for a measurement to be wrong.
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
W, H = 1600, 950

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

SIZE_FLOOR = 12.0          # the operator's metadata floor, in REAL px
CONTRAST_BODY = 4.5
CONTRAST_LARGE = 3.0


def _day(n: int = 0) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + n * 86400))


#: The agenda is served its REAL widget.js and real-shaped data — a calendar grid is where the smallest type
#: in the product lives (day letters, the hour gutter, an event's time), so a screen without one measures the
#: comfortable half and calls it a pass.
def _agenda_data():
    return {
        "date": _day(), "now": "12:00", "mission": "", "plan": {"blocks": [], "focus": []},
        "active": None, "todayIndex": 0, "projects": [], "view": None,
        "meetings": [
            {"date": _day(), "startTime": "17:00", "endTime": "18:00", "title": "Dentista",
             "status": "confirmed"},
            {"date": _day(1), "startTime": "10:00", "endTime": "11:00", "title": "Hacienda",
             "status": "pending", "attendees": ["Ana", "Luis"], "reminder": "30m"}],
        "days": [{"date": _day(i), "label": "X", "weekday": "X",
                  "plan": {"blocks": [], "focus": [], "summary": "", "coaching": [], "warnings": []}}
                 for i in range(7)],
        "calendars": [{"id": "google", "label": "Google Calendar", "status": "unconfigured"},
                      {"id": "icloud", "label": "iCloud (Apple)", "status": "unavailable"},
                      {"id": "caldav", "label": "CalDAV (Outlook, Fastmail…)", "status": "unavailable"}],
        # V2-746 — and the tasks half, which the audit now walks into. Without rows the pane renders its
        # header and nothing else, so every label this pass exists to measure would go unmeasured while the
        # pass reported a clean sweep: an audit over an empty table is the shape of a green test measuring
        # air. Two lists so the zebra's even row is on screen, one finished item so the struck-through ink
        # is measured too, and one carrying a date so the «Cuándo» cell exists.
        "tasks": {
            "lists": [{"id": "general", "name": "General", "no": 1, "builtin": True, "total": 1, "done": 0},
                      {"id": "tl_obra", "name": "Obra", "no": 2, "builtin": False, "total": 3, "done": 1}],
            "items": {
                "general": [{"id": "t1", "no": 1, "title": "Llamar al banco", "status": "todo",
                             "date": "", "time": "", "planned": False}],
                "tl_obra": [
                    {"id": "t2", "no": 1, "title": "Cerrar acuerdo", "status": "done",
                     "date": "", "time": "", "planned": False},
                    {"id": "t3", "no": 2, "title": "Transferencia", "status": "todo",
                     "date": "", "time": "", "planned": False},
                    {"id": "t4", "no": 3, "title": "Crear la cuenta nueva", "status": "todo",
                     "date": _day(1), "time": "17:00", "planned": False}]},
            "view": None},
        "warnings": [], "coaching": []}


STUB_JS = ('export function render(el, data){ el.style.minHeight = "240px";'
           ' el.textContent = "W:" + ((data && data.title) || "?"); }')
ROUTE_RE = re.compile(
    r"^https?://[^/]+/(widgets(/.*)?|api/(canvas/.*|desktop/epoch|client-log|run|status|ui-event))(\?.*)?$")

_AUDIT = r"""() => {
  const px = v => parseFloat(v) || 0;
  // A color-mix() resolves to `color(srgb 0.54 0.44 0.89 / .5)` — components 0..1, NOT 0..255. Reading it
  // with the rgb() parser turns a lilac into near-black and invents a failure that is not there.
  const parse = c => {
    c = (c || '').trim(); if (!c || c === 'transparent') return null;
    const m = c.match(/-?[\d.]+(?:e-?\d+)?%?/g); if (!m) return null;
    const num = (v, scale) => v.endsWith('%') ? parseFloat(v) / 100 * scale : parseFloat(v);
    if (/^color\(/.test(c)) {
      if (!/^color\(\s*srgb/.test(c)) return null;       // another space would need a real conversion
      return {r: num(m[0],1)*255, g: num(m[1],1)*255, b: num(m[2],1)*255,
              a: m.length > 3 ? num(m[3],1) : 1};
    }
    return {r: num(m[0],255), g: num(m[1],255), b: num(m[2],255), a: m.length > 3 ? num(m[3],1) : 1};
  };
  const over = (fg, bg) => ({r: fg.r*fg.a + bg.r*(1-fg.a), g: fg.g*fg.a + bg.g*(1-fg.a),
                             b: fg.b*fg.a + bg.b*(1-fg.a), a: 1});
  const lin = c => { c /= 255; return c <= .04045 ? c/12.92 : Math.pow((c+.055)/1.055, 2.4); };
  const lum = c => .2126*lin(c.r) + .7152*lin(c.g) + .0722*lin(c.b);
  const ratio = (a, b) => { const la = lum(a), lb = lum(b);
    return (Math.max(la,lb) + .05) / (Math.min(la,lb) + .05); };
  // the ground a glyph is really drawn on: every translucent layer up to the page, composited bottom-up
  const ground = el => {
    const stack = []; let n = el;
    while (n && n.nodeType === 1) { const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) { stack.push(c); if (c.a === 1) break; } n = n.parentElement; }
    let base = {r:0, g:0, b:0, a:1};
    for (let i = stack.length - 1; i >= 0; i--) base = over(stack[i], base);
    return base;
  };
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const name = el => (el.className && typeof el.className === 'string'
      ? '.' + el.className.split(/\s+/).filter(Boolean).slice(0,2).join('.') : el.tagName);
  const out = [], seen = new Set();
  document.querySelectorAll('*').forEach(el => {
    // only elements with their OWN text, so a wrapper is never reported for its children's words
    let own = ''; for (const n of el.childNodes) if (n.nodeType === 3) own += n.textContent;
    own = own.trim(); if (own.length < 2 || !vis(el)) return;
    let p = el, chain = 1;
    while (p && p.nodeType === 1) { chain *= px(getComputedStyle(p).opacity) || 1; p = p.parentElement; }
    if (chain < .05) return;                              // deliberately hidden, not deliberately faint
    const s = getComputedStyle(el);
    let fg = parse(s.color); if (!fg) return;
    const bg = ground(el);
    fg = over({...fg, a: fg.a * chain}, bg);               // an ancestor's opacity dims the INK, not the rule
    const size = px(s.fontSize), weight = +s.fontWeight || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const key = name(el) + '|' + Math.round(size) + '|' + own.slice(0, 12);
    if (seen.has(key)) return; seen.add(key);
    const classes = (el.className && typeof el.className === 'string')
        ? el.className.split(/\s+/).filter(Boolean) : [];
    out.push({what: name(el) + ' « ' + own.replace(/\s+/g,' ').slice(0,30) + ' »', classes,
              size: +size.toFixed(1), weight, ratio: +ratio(fg, bg).toFixed(2),
              floor: large ? 3 : 4.5,
              fg: `rgb(${fg.r|0},${fg.g|0},${fg.b|0})`, bg: `rgb(${bg.r|0},${bg.g|0},${bg.b|0})`});
  });
  return out;
}"""

_SEED_CHAT = """() => {
  const l = document.querySelector('.cw-list');
  const mk = (c, t) => { const d = document.createElement('div'); d.className = 'cw-msg ' + c;
                         d.textContent = t; l.appendChild(d); };
  mk('you', 'Ponme la agenda de esta semana, por favor');
  mk('agent', 'Aqui la tienes: tienes dos citas, el dentista hoy a las 17:00 y Hacienda manana.');
  mk('sys', 'restaurado');
  mk('peer', 'Un mensaje de otro cluster');
}"""


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _route(r):
    path = re.sub(r"^https?://[^/]+", "", r.request.url).split("?", 1)[0]
    data = {"agenda": _agenda_data(), "musica": {"title": "Musica"}}

    def j(obj):
        r.fulfill(status=200, content_type="application/json", body=json.dumps(obj))

    if path == "/widgets":
        return j({"widgets": [{"id": w, "size": {"w": 900, "h": 620}} for w in data]})
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
            if wid == "agenda":
                with open(os.path.join(ENGINE, "widgets", "agenda", "widget.js"), encoding="utf-8") as fh:
                    return r.fulfill(status=200, content_type="application/javascript", body=fh.read())
            return r.fulfill(status=200, content_type="application/javascript", body=STUB_JS)
        if kind == "manifest":
            return j({"id": wid})
        return j(data.get(wid, {"title": wid}))
    return r.fallback()


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
    rows, errors = [], []
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = b.new_context(viewport={"width": W, "height": H}).new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.route(ROUTE_RE, _route)
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            pg.wait_for_timeout(2400)
            pg.evaluate("() => document.querySelectorAll('.boot-ovl,.lang-onb,.lang-onb-veil')"
                        ".forEach(e => e.remove())")
            pg.evaluate("() => window.zaelar.show('agenda')")
            pg.wait_for_timeout(900)
            pg.evaluate("() => window.zaelar.panel('chat')")
            pg.wait_for_timeout(400)
            # V2-761 — below 400px the wall's standing tab name gives way so five icon tabs fit, which left the
            # default 320px box with no words of its own to measure. 480px is the narrow layout WITH its name.
            pg.evaluate("() => { const w = document.querySelector('#chatwall'); if (w) w.style.width = '480px'; }")
            pg.wait_for_timeout(250)
            pg.evaluate(_SEED_CHAT)
            pg.wait_for_timeout(300)
            rows += [dict(r, screen="desk+agenda") for r in pg.evaluate(_AUDIT)]
            # The connectors screen the operator named in the pass before this one. Reached by CLASS, never
            # by its label: the first version matched /onect/i, which finds «Conectores» and misses
            # «Connectors», so under the shell's default language this pass silently re-measured the
            # calendar. `.agcalbtn` is the header's own door into that screen and there is exactly one.
            # V2-746 — the agenda's OTHER half. The audit has only ever seen the calendar, and the memory
            # this test left behind said so in as many words: «extender 4.170 por widget seguramente
            # encuentre más tipografía bajo 12px». It did — four labels of the tasks table were under the
            # floor the moment they were written, and nothing would have said so. Reached by the section
            # button's `data-sec`, which is language-independent, for the same reason the connectors screen
            # below is reached by class: matching a LABEL re-measures the previous screen in silence.
            pg.evaluate("""() => { const b = document.querySelector('.agsecb[data-sec="tasks"]');
                                   if (b) b.click(); }""")
            pg.wait_for_timeout(500)
            rows += [dict(r, screen="agenda+tasks") for r in pg.evaluate(_AUDIT)]
            pg.evaluate("""() => { const b = document.querySelector('.agsecb[data-sec="agenda"]');
                                   if (b) b.click(); }""")
            pg.wait_for_timeout(400)
            pg.evaluate("""() => { const b = document.querySelector('.agcalbtn'); if (b) b.click(); }""")
            pg.wait_for_timeout(500)
            rows += [dict(r, screen="connectors") for r in pg.evaluate(_AUDIT)]
            b.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()
    return {"rows": rows, "errors": errors}


def _fmt(rows):
    return "\n".join(
        f"    {r['ratio']:5.2f} (needs {r['floor']})  {r['size']}px/{r['weight']}  "
        f"{r['fg']} on {r['bg']}  [{r['screen']}] {r['what']}" for r in rows)


def test_the_audit_actually_saw_the_screen(measured):
    """Every assertion below is «nothing was found»; this is the one that fails if nothing was LOOKED at.
    Without it a shell that failed to boot would report a perfect, empty pass — the shape of a green test
    that measures air.

    ⚠️ Its first version asserted `{r["screen"]} == {"desk+agenda", "connectors"}` — and that label is
    written by the HARNESS, in Python, whichever screen the browser is actually showing. Disarming the
    Conectores button left it green: it was checking its own bookkeeping. Each pass is now anchored to an
    element that exists ONLY on the screen it claims to have measured.
    """
    assert not measured["errors"], "; ".join(measured["errors"][:3])
    rows = measured["rows"]
    assert len(rows) >= 60, f"only {len(rows)} text elements measured — the screen did not come up"
    desk = [r for r in rows if r["screen"] == "desk+agenda"]
    conn = [r for r in rows if r["screen"] == "connectors"]
    # Matched on the class TOKEN, never as a substring of the label: `.aghourX` contains `.aghour`, so a
    # substring anchor survives the very rename it is supposed to catch (measured — that disarm came back
    # green). And the anchors are PRODUCT-rendered elements, never the bubbles this harness seeds itself.
    def has(rows_, cls):
        return any(cls in r["classes"] for r in rows_)
    assert has(desk, "aghour"), \
        "the calendar grid never rendered — the smallest type in the product went unmeasured"
    assert has(desk, "cw-tabname"), "the chat wall never opened"
    assert has(conn, "agcalname"), \
        "the connectors screen never opened — that pass measured the calendar again"
    # V2-746 — the tasks half, anchored the same way: `agt-list` is a row of the lists table and exists on
    # no other screen, so this cannot go green over a pass that re-measured the calendar.
    tasks = [r for r in rows if r["screen"] == "agenda+tasks"]
    # Anchored on elements that carry their OWN text: this audit walks leaf text (`own.length < 2` is
    # skipped), so `.agt-list` and `.agt-cols` are containers it can never record and an anchor on either
    # would fail over a screen that rendered perfectly. `.agt-lname` is a row of the lists pane and
    # `.agt-ino` a numbered row of the items table — one from each half, both of them rows and not chrome,
    # so an empty table cannot pass this either.
    assert has(tasks, "agt-lname"), \
        "the tasks half never opened — that pass measured the calendar again"
    assert has(tasks, "agt-ino"), "the items table rendered no rows — its type went unmeasured"


def test_no_text_on_the_screen_is_under_its_contrast_floor(measured):
    """«lila sobre negro · gris medio sobre negro · labels pequeñas sobre fondos oscuros.» Measured against
    the ground the compositor actually put behind each glyph, with the inherited opacity chain folded into
    the ink — a label at `opacity:.4` is dim whatever its colour token says."""
    bad = [r for r in measured["rows"] if r["ratio"] < r["floor"]]
    assert not bad, f"{len(bad)} text elements under the WCAG AA floor:\n{_fmt(bad)}"


def test_nothing_is_painted_below_the_size_floor(measured):
    """«metadata pequeña: no bajar de 12px.» Enforced in REAL px, after the root-size knob has been applied,
    because that is the only number the reader's eye actually meets."""
    small = [r for r in measured["rows"] if r["size"] < SIZE_FLOOR]
    assert not small, (f"{len(small)} text elements under {SIZE_FLOOR}px:\n"
                       + "\n".join(f"    {r['size']}px/{r['weight']}  [{r['screen']}] {r['what']}"
                                   for r in sorted(small, key=lambda r: r["size"])))


def test_the_tightest_text_still_has_real_headroom(measured):
    """A screen that sits exactly ON the floor everywhere passes the two tests above and is still tiring to
    read for hours, which is the thing the operator actually asked for. So the WORST ratio on the screen
    carries its own floor: comfortably clear of AA, not balanced on it.

    5.5 is not a standard — it is a ratchet set just under what the screen measures today (6.55), so this
    goes red on the drift that a per-case AA check would let through one element at a time.
    """
    worst = min(measured["rows"], key=lambda r: r["ratio"])
    assert worst["ratio"] >= 5.5, f"the tightest text on the screen is only {worst['ratio']}:1 — {_fmt([worst])}"


def test_a_filled_accent_surface_never_carries_white_text(measured):
    """The accent was LIGHTENED so it stops being the worst text colour on the screen — which makes white on
    top of it worse, not better (2.1:1). The rule that goes with the lighter accent, and the reason this is
    a test and not a comment: text on a filled accent/status surface is the DARK ink, everywhere.

    Checked by CONSEQUENCE rather than by grepping for `#fff`: any near-white ink sitting on a mid-to-light
    ground is the failure, whichever declaration produced it.
    """
    def chan(rgb):
        return [int(x) for x in re.findall(r"\d+", rgb)]
    offenders = []
    for r in measured["rows"]:
        fg, bg = chan(r["fg"]), chan(r["bg"])
        if min(fg) > 200 and 90 < sum(bg) / 3 < 220:
            offenders.append(r)
    assert not offenders, f"white ink on a light filled surface:\n{_fmt(offenders)}"
