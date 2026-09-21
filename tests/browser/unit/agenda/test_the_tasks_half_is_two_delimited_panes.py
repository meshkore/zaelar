"""V2-746 — RENDERED: the tasks half is two delimited panes, and the ＋ cannot scroll away.

The operator, 2026-09-21, asking for a restyling of this half and saying what was wrong with it:

    «Me gustaría que la agenda tuviera un poco más aspecto… que tuviera un poco más aspecto tipo Excel…
     que se delimiten mejor las listas de tareas de la izquierda, a la derecha también todo el formato de
     la lista, los botones… El botón de nueva lista, pues abajo no está bien porque **cuando tengamos 100
     listas no se va a ver**. Esa barra segunda que pone agenda y tareas, quizás debería ser una línea de
     subheader más consistente. **Por si hay que crear algo más ahí.**»

Every claim below is a STRUCTURAL one, because those are the ones that can regress without anybody noticing
and the ones a screenshot cannot defend. How it looks is his call and he will say so; whether the ＋ is
still on screen under a hundred lists is arithmetic, and arithmetic belongs here.

What is deliberately NOT asserted: colours, radii, spacing, the zebra's exact tint. Pinning those would
turn the next design change into a test-editing exercise, which is how a suite stops protecting anything.
The one visual property that IS pinned lives elsewhere and is measured rather than described: node 4.170
now walks this half and holds it to the contrast and 12px floors (extended in this same batch, and it
caught the list numerals at 3.67:1 the moment they were written).
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
from tests.waiting import until_sync  # noqa: E402

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _d(n: int = 0) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + n * 86400))


def _data(n_lists: int = 3):
    """`n_lists` so the «100 listas» case is the SAME data shape at a different size — the objection is
    about volume, so the test that answers it has to be able to turn the volume up."""
    # The counts are deliberately of DIFFERENT widths — «1/4», «12/108», «100/100». With every row showing
    # the same number of digits an `auto` column lines up by accident, and the disarm that turned the fixed
    # column back into `auto` stayed GREEN over exactly that: the fixture was measuring its own uniformity.
    lists = [{"id": "general", "name": "General", "no": 1, "builtin": True, "total": 0, "done": 0}]
    for i in range(2, n_lists + 1):
        total = i * 9
        lists.append({"id": f"tl_{i}", "name": f"Lista {i}", "no": i, "builtin": False,
                      "total": total, "done": total if i == 3 else i})
    return {"date": _d(), "now": "12:00", "mission": "", "plan": {"blocks": [], "focus": []},
            "active": None, "todayIndex": 0, "projects": [], "view": None, "meetings": [],
            "days": [{"date": _d(i), "label": "X", "weekday": "X",
                      "plan": {"blocks": [], "focus": [], "summary": "", "coaching": [], "warnings": []}}
                     for i in range(7)],
            "calendars": [], "warnings": [], "coaching": [],
            "tasks": {"lists": lists,
                      "items": {"tl_2": [
                          {"id": "a", "no": 1, "title": "Cerrar acuerdo", "status": "done",
                           "date": "", "time": "", "planned": False},
                          {"id": "b", "no": 2, "title": "Transferencia", "status": "todo",
                           "date": "", "time": "", "planned": False},
                          {"id": "c", "no": 3, "title": "Abrir la cuenta", "status": "todo",
                           "date": _d(2), "time": "17:00", "planned": False}]},
                      "view": None}}


@pytest.fixture(scope="module")
def _page():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _listening():
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close(); return True
        except OSError:
            return False

    until_sync(_listening, f"the static server on 127.0.0.1:{port} to accept a connection", timeout_s=15)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1160, "height": 760})
            page._hb_url = f"http://127.0.0.1:{port}/widgets/agenda/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/agenda/"
            page._hb_port = port
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data, *, card_w=1080, card_h=620):
    """The REAL palette is linked, not the fallbacks baked into the widget: a pane's surface only reads as
    a step of the ladder against the other steps, and the fallbacks are what renders when it is missing."""
    page.goto(page._hb_origin)
    page.set_content(
        f"<link rel='stylesheet' href='http://127.0.0.1:{page._hb_port}/frontend/app/core/palette.css'>"
        f"<style>html,body{{margin:0;background:var(--canvas)}}"
        f".card{{width:{card_w}px;height:{card_h}px;background:var(--hb-bg);padding:16px;"
        f"box-sizing:border-box;display:flex;flex-direction:column}}</style>"
        f"<div class='card'><div id='w' style='flex:1 1 auto;min-height:0'></div></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__ctx = { action: (n, p) => { window.__calls.push([n, p || {}]);
                                                  return Promise.resolve({ok: true}); },
                              top: () => {}, running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_url, data])
    page.click('.agsecb[data-sec="tasks"]')
    page.wait_for_timeout(120)


def _box(page, sel):
    return page.evaluate(
        """(s) => { const e = document.querySelector(s); if (!e) return null;
                    const r = e.getBoundingClientRect();
                    return {x: r.x, y: r.y, w: r.width, h: r.height, b: r.bottom, rt: r.right}; }""", sel)


# ── «el botón de nueva lista… cuando tengamos 100 listas no se va a ver» ────────────────────────────────

def test_the_plus_is_in_the_column_HEADER_and_not_under_the_rows(_page):
    _mount(_page, _data())
    plus, head, rows = _box(_page, ".agt-plus"), _box(_page, ".agt-sidehead"), _box(_page, ".agt-rows")
    assert plus and head and rows, "the ＋, the column header or the scroller is missing"
    assert head.get("y") <= plus["y"] and plus["b"] <= head["b"] + 1, "the ＋ is not inside the header bar"
    assert plus["b"] <= rows["y"] + 1, "the ＋ is still below the rows — it will scroll away with them"


def test_the_plus_SURVIVES_a_hundred_lists(_page):
    """The objection, answered with his own number. The rows scroll; the ＋ does not move, because it is a
    sibling of the scroller and not a row inside it."""
    _mount(_page, _data(100))
    assert _page.locator(".agt-side .agt-list").count() == 100
    before = _box(_page, ".agt-plus")
    _page.evaluate("() => { const r = document.querySelector('.agt-rows'); r.scrollTop = r.scrollHeight; }")
    _page.wait_for_timeout(120)
    after = _box(_page, ".agt-plus")
    side = _box(_page, ".agt-side")
    assert _page.evaluate("() => document.querySelector('.agt-rows').scrollTop") > 100, \
        "the rows never scrolled — this measured nothing"
    assert abs(after["y"] - before["y"]) < 1, "the ＋ moved when the rows scrolled"
    assert side["y"] <= after["y"] and after["b"] <= side["b"], "the ＋ is outside the visible column"


# ── «que se delimiten mejor… delimitando bien lo que es la columna de la izquierda» ─────────────────────

def test_each_half_is_a_PANE_with_its_own_edge_and_its_own_surface(_page):
    _mount(_page, _data())
    look = _page.evaluate(
        """() => { const g = s => { const c = getComputedStyle(document.querySelector(s));
                     return {bw: parseFloat(c.borderTopWidth), bg: c.backgroundColor,
                             r: parseFloat(c.borderTopLeftRadius)}; };
                   return {side: g('.agt-side'), main: g('.agt-main'),
                           card: getComputedStyle(document.querySelector('.card')).backgroundColor}; }""")
    for half in ("side", "main"):
        assert look[half]["bw"] >= 1, f"the {half} pane has no edge"
        assert look[half]["r"] >= 4, f"the {half} pane is not a rounded surface"
        assert look[half]["bg"] not in ("rgba(0, 0, 0, 0)", "transparent"), \
            f"the {half} pane has no surface of its own — it is still the card's background"
    assert look["side"]["bg"] != look["main"]["bg"], \
        "both panes sit on the same step — nothing says where one ends and the other begins"
    assert look["side"]["bg"] != look["card"], "the lists column repeats the card's own surface"


def test_the_two_panes_fill_the_card_instead_of_hugging_their_rows(_page):
    """A column that stops under its last row is not a column. It measured 258px inside a 620px card, which
    is exactly the «no se delimita» he was looking at — the body was not a flex column, so the panes sized
    to their content."""
    _mount(_page, _data(), card_h=620)
    side, main, body = _box(_page, ".agt-side"), _box(_page, ".agt-main"), _box(_page, ".agbody.tasks")
    assert side["h"] > 400, f"the lists column is only {side['h']:.0f}px tall inside a 620px card"
    assert abs(side["h"] - main["h"]) < 2, "the two panes are different heights"
    assert abs(side["h"] - body["h"]) < 2, "the panes do not fill the body"


# ── «un poco más aspecto tipo Excel» — rows, not chips ─────────────────────────────────────────────────

def test_the_rows_are_CONTIGUOUS_and_ruled_rather_than_floating(_page):
    """A table is rows that touch, separated by a line. Chips are rows separated by air. The gap between
    consecutive rows is the whole difference and it is measurable."""
    _mount(_page, _data(4))
    gaps = _page.evaluate(
        """(sel) => { const rs = [...document.querySelectorAll(sel)];
                      const out = [];
                      for (let i = 1; i < rs.length; i++)
                        out.push(rs[i].getBoundingClientRect().top - rs[i-1].getBoundingClientRect().bottom);
                      return out; }""", ".agt-side .agt-list")
    assert gaps, "fewer than two list rows — this measured nothing"
    assert all(g < 1.5 for g in gaps), f"the rows still float apart: gaps {gaps}"
    ruled = _page.evaluate(
        """() => { const c = getComputedStyle(document.querySelector('.agt-list'));
                   return parseFloat(c.borderBottomWidth); }""")
    assert ruled >= 1, "the rows touch but nothing rules them apart"


def test_the_items_table_has_a_LABEL_row(_page):
    _mount(_page, _data())
    _page.click('.agt-list[data-list="tl_2"]')
    _page.wait_for_timeout(120)
    cols = _page.locator(".agt-cols")
    assert cols.count() == 1, "the items table has no label row"
    labels = _page.evaluate(
        """() => [...document.querySelectorAll('.agt-cols i')].map(e => (e.textContent || '').trim())""")
    assert [x for x in labels if x], f"the label row is empty: {labels}"
    head, first = _box(_page, ".agt-cols"), _box(_page, ".agt-items .agt-item")
    assert head["b"] <= first["y"] + 1, "the label row is not above the rows it labels"


def test_the_numeric_columns_LINE_UP_down_the_table(_page):
    """«1/3» under «12/40» on the slash, and «1.» under «10.» — that alignment is the spreadsheet feel, and
    it comes from a fixed grid plus tabular figures, neither of which survives a careless edit."""
    _mount(_page, _data(12))
    # The LEFT edge, not the right one. With `auto` the column shrinks to each row's own digits and the
    # cell is still flush right, so every row shares a right edge and the first version of this assertion
    # could not tell the two apart — it stayed green over the disarm that took the fixed column away. What a
    # COLUMN means is that it starts in the same place too: the names all truncate at one width and the
    # counts all begin at one x. That is the property, and it is the one `auto` cannot fake.
    edges = _page.evaluate(
        """() => [...document.querySelectorAll('.agt-side .agt-count')].map(e => {
             const r = e.getBoundingClientRect();
             return [Math.round(r.left), Math.round(r.right)]; })""")
    assert len(edges) >= 10, f"only {len(edges)} rows — this measured nothing"
    widths = {e[1] - e[0] for e in edges}
    assert len({e[0] for e in edges}) == 1, \
        f"the counts do not start in the same column: {sorted({e[0] for e in edges})}"
    assert len({e[1] for e in edges}) == 1, f"the counts do not share a right edge: {sorted({e[1] for e in edges})}"
    assert len(widths) == 1, f"the count column is a different width on different rows: {sorted(widths)}"
    # …and the fixture really does hold counts of different lengths, or the three asserts above are trivia.
    texts = _page.evaluate(
        """() => [...document.querySelectorAll('.agt-side .agt-count')].map(e => e.textContent.trim())""")
    assert len({len(t) for t in texts}) > 1, f"every count is the same length — the fixture proves nothing: {texts}"
    mono = _page.evaluate(
        """() => { const c = getComputedStyle(document.querySelector('.agt-count'));
                   return {f: c.fontFamily, n: c.fontVariantNumeric}; }""")
    assert "mono" in mono["f"].lower(), f"the count column is not monospaced: {mono['f']}"


def test_a_rows_own_controls_share_ONE_column(_page):
    """They used to sit after the title, so they drifted left and right with the length of each task."""
    _mount(_page, _data())
    _page.click('.agt-list[data-list="tl_2"]')
    _page.wait_for_timeout(120)
    lefts = _page.evaluate(
        """() => [...document.querySelectorAll('.agt-items .agt-ops')]
                  .map(e => Math.round(e.getBoundingClientRect().left))""")
    assert len(lefts) == 3, f"expected one control group per row, got {len(lefts)}"
    assert len(set(lefts)) == 1, f"the row controls drift with the title: {sorted(set(lefts))}"


def test_a_row_with_NO_date_keeps_the_when_column_open(_page):
    """A grid column that some rows skip is a grid whose later columns slide left on those rows — and the
    alignment above is the whole point of the change."""
    _mount(_page, _data())
    _page.click('.agt-list[data-list="tl_2"]')
    _page.wait_for_timeout(120)
    assert _page.locator(".agt-items .agt-item").nth(1).locator(".agt-when").count() == 0, \
        "the fixture's second item is supposed to have no date"
    cells = _page.evaluate(
        """() => [...document.querySelectorAll('.agt-items .agt-item')]
                  .map(r => r.children.length)""")
    assert len(set(cells)) == 1, f"rows carry different numbers of cells: {cells}"


# ── «una línea de subheader más consistente. Por si hay que crear algo más ahí» ─────────────────────────

def test_the_subheader_is_a_BAND_across_the_card_and_not_a_floating_pill(_page):
    _mount(_page, _data())
    sub, body = _box(_page, ".agsub"), _box(_page, ".agbody.tasks")
    assert sub, "there is no subheader band"
    assert abs(sub["w"] - body["w"]) < 2, \
        f"the subheader is {sub['w']:.0f}px over a {body['w']:.0f}px body — still a pill, not a line"
    ruled = _page.evaluate(
        """() => parseFloat(getComputedStyle(document.querySelector('.agsub')).borderBottomWidth)""")
    assert ruled >= 1, "the band does not close on a rule"


def test_the_band_has_a_SLOT_and_the_tasks_half_fills_it_with_what_it_holds(_page):
    """«Por si hay que crear algo más ahí» — the slot is the point of the change, so it is the thing pinned:
    it exists, it is on the far side of the tabs, and it says something true about the half below it."""
    _mount(_page, _data(4))
    meta = _page.locator('.agsub-meta[data-meta="tasks"]')
    assert meta.count() == 1, "the band has no right-hand slot on the tasks half"
    txt = meta.inner_text()
    assert "4" in txt, f"the slot does not count the lists: {txt!r}"
    # Lists 2, 3 and 4 hold 18, 27 and 36 items with 2, 27 and 4 done → 16 + 0 + 32 = 48 still open.
    assert "48" in txt, f"the slot does not count what is still open: {txt!r}"
    tabs, slot = _box(_page, ".agsec"), _box(_page, ".agsub-meta")
    assert slot["x"] > tabs["rt"], "the slot is not on the far side of the tabs"


def test_the_CALENDAR_half_leaves_the_slot_empty(_page):
    """An empty slot costs no node: the band is shared chrome, and the calendar has nothing to put there
    yet. If something is ever rendered there by accident, this is what says so."""
    _mount(_page, _data())
    _page.click('.agsecb[data-sec="agenda"]')
    _page.wait_for_timeout(150)
    assert _page.locator(".agsub").count() == 1, "the band does not survive the other half"
    assert _page.locator(".agsub-meta").count() == 0, "the calendar half is rendering something in the slot"


# ── the restyle did not break the half it restyled ─────────────────────────────────────────────────────

def test_a_finished_list_reads_as_finished_without_reading_as_selected(_page):
    """«Regalos 2/2» was a full accent bar, and so is a selected row out of the corner of the eye."""
    _mount(_page, _data(4))
    full = _page.evaluate(
        """() => [...document.querySelectorAll('.agt-side .agt-list')].map(r => {
             const p = r.querySelector('.agt-prog');
             return {full: p.classList.contains('full'),
                     fill: getComputedStyle(p.querySelector('span')).backgroundColor}; })""")
    done = [f for f in full if f["full"]]
    assert len(done) == 1, f"exactly one fixture list is complete, marked {len(done)}"
    others = {f["fill"] for f in full if not f["full"]}
    assert done[0]["fill"] not in others, \
        "a finished list paints the same colour as one in progress"


def test_clicking_a_list_still_reaches_the_widgets_action(_page):
    """The restyle moved nodes around; a pane that looks right and answers nothing is the worse failure."""
    _mount(_page, _data())
    _page.click('.agt-list[data-list="tl_2"]')
    _page.wait_for_timeout(120)
    _page.fill('.agt-add input[data-add="task"]', "Aceite")
    _page.click('.agt-add button[data-a2="additem"]')
    _page.wait_for_timeout(150)
    calls = _page.evaluate("() => window.__calls")
    assert ["add_task", {"title": "Aceite", "list": "tl_2"}] in calls, calls


def test_the_new_list_form_still_opens_and_still_asks_the_widget(_page):
    _mount(_page, _data())
    _page.click('.agt-plus')
    _page.wait_for_timeout(120)
    assert _page.locator(".agt-newl input").count() == 1, "the ＋ no longer opens the inline form"
    head = _box(_page, ".agt-sidehead")
    box = _box(_page, ".agt-newl input")
    assert head["y"] <= box["y"] and box["b"] <= head["b"] + 1, "the form escaped the header bar"
    _page.fill(".agt-newl input", "Viaje a Roma")
    _page.press(".agt-newl input", "Enter")
    _page.wait_for_timeout(150)
    assert ["add_list", {"name": "Viaje a Roma"}] in _page.evaluate("() => window.__calls")


# ── the handle he reads before he speaks has to be readable ────────────────────────────────────────────

_RATIO = r"""(sel) => {
  const parse = c => { c = (c || '').trim(); if (!c || c === 'transparent') return null;
    const m = c.match(/-?[\d.]+(?:e-?\d+)?%?/g); if (!m) return null;
    const num = (v, sc) => v.endsWith('%') ? parseFloat(v) / 100 * sc : parseFloat(v);
    if (/^color\(/.test(c)) { if (!/^color\(\s*srgb/.test(c)) return null;
      return {r: num(m[0],1)*255, g: num(m[1],1)*255, b: num(m[2],1)*255, a: m.length>3 ? num(m[3],1) : 1}; }
    return {r:+m[0], g:+m[1], b:+m[2], a: m.length>3 ? +m[3] : 1}; };
  const over = (f,b) => ({r: f.r*f.a + b.r*(1-f.a), g: f.g*f.a + b.g*(1-f.a),
                          b: f.b*f.a + b.b*(1-f.a), a: 1});
  const lum = c => { const f = v => { v /= 255;
                       return v <= .03928 ? v/12.92 : Math.pow((v+.055)/1.055, 2.4); };
                     return .2126*f(c.r) + .7152*f(c.g) + .0722*f(c.b); };
  const el = document.querySelector(sel); if (!el) return null;
  let bg = null, stack = [];
  for (let n = el; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor);
    if (c && c.a > 0) stack.push(c); if (c && c.a === 1) break; }
  bg = stack.pop() || {r:22, g:25, b:30, a:1};
  while (stack.length) bg = over(stack.pop(), bg);
  const ink = over(parse(getComputedStyle(el).color), bg);
  const a = lum(ink), b = lum(bg);
  return +(((Math.max(a,b) + .05) / (Math.min(a,b) + .05)).toFixed(2)); }"""


def test_the_LIST_NUMERAL_is_readable_in_both_states(_page):
    """«Ábreme la lista número 3» only works if the 3 can be read, and this is the one pairing V2-691 called
    the tightest thing on the screen: the accent used as small text over its own tint.

    It is measured HERE and not by node 4.170 for a reason worth writing down. That audit walks leaf text
    and skips anything under two characters (`own.length < 2`), so a one-digit badge is invisible to it —
    and the disarm that put the accent ink back measured 3.67:1 on a selected row, under AA, while the
    product-wide audit stayed green. A floor that cannot see the element it would fail on is not a floor.
    """
    _mount(_page, _data(4))
    plain = _page.evaluate(_RATIO, ".agt-list:not(.on) .agt-no")
    _page.click('.agt-list[data-list="tl_2"]')
    _page.wait_for_timeout(120)
    chosen = _page.evaluate(_RATIO, ".agt-list.on .agt-no")
    assert plain and chosen, "the numerals are not on screen"
    # 5.5 is node 4.170's own headroom floor, not bare AA: a screen balanced on 4.5 passes every per-element
    # check and still tires the eye, which is the thing the operator actually asked for.
    assert plain >= 5.5, f"an unselected list numeral reads at {plain}:1"
    assert chosen >= 5.5, f"the SELECTED list numeral reads at {chosen}:1 — it is the one he is looking at"
