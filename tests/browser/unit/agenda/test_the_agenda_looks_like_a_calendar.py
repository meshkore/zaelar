# V2-643 — the agenda in the shapes everybody already knows. The operator's own report, with two screenshots:
# «se muestra muy pequeño, se cortan las palabras de abajo», the header undifferentiated, the connector icons
# «tan pequeños y apelmazados que no se sabe qué significa ninguno», an absurd paragraph as a description, and
# the spec — «una vista semanal tiene que mostrarnos cada uno de los días de la semana con los ítems dentro de
# cada columna… en varios colores, con varias intensidades… un simbolito que marque si tienen notificación…
# si son reuniones, si están confirmadas por la contraparte… cuántas personas».
#
# RENDERED, every case: whether seven columns exist, whether a chip lands at the pixel its hour deserves,
# whether two meetings at the same hour sit SIDE BY SIDE instead of on top of each other, and whether the
# control bar survives inside a real card are questions only layout answers. The clipping cases mount the REAL
# card chrome (.hb-win > .hb-scroll > root, copied verbatim) — the V2-608 fixture lesson: a harness whose DOM
# differs from the product's measures a different product.
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]

# Card chrome, copied VERBATIM from frontend/app/widgets/desktop.js.
_CARD_CSS = """
  .hb-win{position:fixed;left:20px;top:20px;display:flex;flex-direction:column;
          padding:30px 16px 16px;overflow:hidden;box-sizing:border-box;background:#fff}
  .hb-scroll{flex:1 1 auto;min-height:0;overflow:auto}
"""


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _d(n: int = 0) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + n * 86400))


def _days(n: int = 7):
    return [{"date": _d(i), "label": "X", "weekday": "X",
             "plan": {"blocks": [], "focus": [], "summary": "", "coaching": [], "warnings": []}}
            for i in range(n)]


def _data(**over):
    d = {"date": _d(), "now": "12:00", "mission": "", "plan": {"blocks": [], "focus": []},
         "active": None, "days": _days(), "todayIndex": 0, "meetings": [], "projects": [],
         "view": None, "calendars": [], "warnings": [], "coaching": []}
    d.update(over)
    return d


def _meet(title, *, day=0, start="10:00", end="11:00", **extra):
    m = {"title": title, "date": _d(day), "startTime": start, "endTime": end}
    m.update(extra)
    return m


@pytest.fixture(scope="module")
def _page():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1100, "height": 800})
            page._hb_url = f"http://127.0.0.1:{port}/widgets/agenda/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/agenda/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data, *, card_w=920, card_h=0):
    """card_h > 0 mounts inside the REAL card chrome at that fixed size."""
    page.goto(page._hb_origin)
    if card_h:
        page.set_content(
            f"<style>{_CARD_CSS}</style>"
            f"<div class='hb-win' style='width:{card_w}px;height:{card_h}px'>"
            f"<div class='hb-scroll'><div id='w'></div></div></div>")
    else:
        page.set_content(f"<div id='w' style='width:{card_w}px'></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__mod = mod;
             window.__ctx = { action: (n, p) => { window.__calls.push([n, p || {}]);
                                                  return Promise.resolve({ok: true}); },
                              top: () => {}, running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_url, data])


# ── the week is SEVEN COLUMNS with the items inside them ────────────────────────────────────────────────

def test_the_week_shows_every_day_as_a_column(_page):
    _mount(_page, _data())
    assert _page.locator(".agtab.on").get_attribute("data-view") == "week"
    assert _page.locator(".agcol").count() == 7, "seven days, seven columns — the operator's own spec"
    heads = _page.locator(".aghead .agdh").all_inner_texts()
    assert len(heads) == 8, "seven day heads plus the hour gutter"
    assert _page.locator(".agdh.today").count() == 1, "today is marked inside the week"


def test_an_event_lands_in_ITS_day_column_at_ITS_hour(_page):
    _mount(_page, _data(meetings=[_meet("Dentista", day=2, start="10:00", end="11:00")]))
    geo = _page.evaluate(
        """() => { const cols=[...document.querySelectorAll('.agcol')];
                   const ev=document.querySelector('.agev');
                   const owner=cols.findIndex(c => c.contains(ev));
                   return {owner, top: ev.offsetTop, height: ev.offsetHeight,
                           cols: cols.length, hours: [...document.querySelectorAll('.aghour')].length}; }""")
    assert geo["owner"] >= 0, "the chip lives INSIDE a day column, not floating over the grid"
    assert geo["top"] > 0, "10:00 is not the top of the grid"
    assert 35 < geo["height"] < 60, f"one hour is about one hour tall, got {geo['height']}"


def test_two_meetings_at_the_same_hour_sit_SIDE_BY_SIDE(_page):
    """Without overlap layout, one of the two is simply invisible — which is a calendar that hides an
    appointment, the worst thing this widget can do."""
    _mount(_page, _data(meetings=[_meet("Dentista", start="10:00", end="11:00"),
                                  _meet("Notario", start="10:30", end="11:30")]))
    boxes = _page.evaluate(
        """() => [...document.querySelectorAll('.agev')].map(e => {
             const r = e.getBoundingClientRect(); return {l: r.left, r: r.right, t: r.top}; })""")
    assert len(boxes) == 2, boxes
    a, b = sorted(boxes, key=lambda x: x["l"])
    assert a["r"] <= b["l"] + 1, "they must not overlap horizontally"


# ── colours and intensities ─────────────────────────────────────────────────────────────────────────────

def test_categories_carry_different_colours_and_a_pending_one_is_outlined(_page):
    _mount(_page, _data(meetings=[
        _meet("Dentista", start="09:00", end="10:00", category="salud", status="confirmed"),
        _meet("Consejo", start="11:00", end="12:00", category="trabajo",
              status="pending", attendees=["Ana", "Luis"]),
    ]))
    info = _page.evaluate(
        """() => [...document.querySelectorAll('.agev')].map(e => ({
             hue: e.style.getPropertyValue('--evc').trim(),
             pending: e.classList.contains('pending'),
             border: getComputedStyle(e).borderTopStyle,
           }))""")
    assert len({i["hue"] for i in info}) == 2, f"a health and a work event are not the same colour: {info}"
    pending = [i for i in info if i["pending"]]
    assert len(pending) == 1 and pending[0]["border"] == "dashed", \
        "a meeting the other side has not confirmed is OUTLINED, the convention every calendar uses"


def test_a_planned_task_block_is_softer_than_a_real_appointment(_page):
    """Intensity is the second axis the operator asked for: a real commitment reads stronger than a block
    the planner placed on its own."""
    days = _days()
    days[0]["plan"]["blocks"] = [{"start": "15:00", "end": "16:00", "label": "Revisar contrato",
                                  "kind": "deep", "taskId": "t1"}]
    _mount(_page, _data(days=days, meetings=[_meet("Dentista", start="09:00", end="10:00")]))
    kinds = _page.evaluate(
        """() => [...document.querySelectorAll('.agev')].map(e => ({
             planned: e.classList.contains('planned'), title: e.textContent }))""")
    assert any(k["planned"] and "contrato" in k["title"] for k in kinds), kinds
    assert any((not k["planned"]) and "Dentista" in k["title"] for k in kinds), kinds


def test_a_meeting_from_the_planner_is_not_drawn_twice(_page):
    """The planner puts meetings in its blocks too. Taking both sources naively paints every appointment
    twice — the same appointment, side by side with itself."""
    days = _days()
    days[0]["plan"]["blocks"] = [{"start": "10:00", "end": "11:00", "label": "Dentista", "kind": "meeting"}]
    _mount(_page, _data(days=days, meetings=[_meet("Dentista", start="10:00", end="11:00")]))
    assert _page.locator(".agev").count() == 1


# ── badges: the bell and how many people ────────────────────────────────────────────────────────────────

def test_a_reminder_shows_a_bell_and_attendees_show_their_number(_page):
    _mount(_page, _data(meetings=[
        _meet("Dentista", start="10:00", end="11:00", remindAt="2026-09-09 08:00",
              attendees=["Ana", "Luis", "Marta"]),
        _meet("Café", start="17:00", end="18:00"),
    ]))
    badged = _page.evaluate(
        """() => [...document.querySelectorAll('.agev')].map(e => ({
             title: (e.querySelector('.agevt')||{}).textContent,
             badges: [...e.querySelectorAll('.agbadge')].map(b => b.textContent.trim()),
             svgs: e.querySelectorAll('.agbadge svg').length }))""")
    dent = [b for b in badged if b["title"] == "Dentista"][0]
    cafe = [b for b in badged if b["title"] == "Café"][0]
    assert dent["svgs"] == 2, "bell + people, both drawn"
    assert "3" in "".join(dent["badges"]), dent
    assert cafe["badges"] == [], "an appointment with nobody and no notice wears no badges"


# ── the detail panel: what a click on an event tells you, and what it can DO ─────────────────────────────

def test_clicking_an_event_opens_its_detail_with_the_real_actions(_page):
    _mount(_page, _data(meetings=[
        _meet("Dentista", start="10:00", end="11:00", location="Clínica Ruiz",
              attendees=["Ana"], status="pending", notes="Llevar la radiografía")]))
    _page.click(".agev")
    panel = _page.locator(".agpanel")
    txt = panel.inner_text()
    assert "Dentista" in txt and "Clínica Ruiz" in txt and "radiografía" in txt and "Ana" in txt
    _page.click(".agpacts button >> nth=0")            # «Ya está confirmada»
    call = _page.evaluate("window.__calls.pop()")
    assert call[0] == "update_meeting" and call[1]["status"] == "confirmed", call


def test_cancelling_an_appointment_asks_first(_page):
    _mount(_page, _data(meetings=[_meet("Dentista", start="10:00", end="11:00")]))
    _page.click(".agev")
    _page.click(".agpacts button.risk")                # «Cancelar cita»
    assert _page.evaluate("window.__calls.length") == 0, "one click must not delete an appointment"
    _page.click(".agpacts button.risk")                # «Sí, cancélala»
    call = _page.evaluate("window.__calls.pop()")
    assert call[0] == "cancel_meeting" and call[1]["title"] == "Dentista", call


# ── the operator's two visible complaints ───────────────────────────────────────────────────────────────

def test_the_calendars_are_named_rows_behind_a_button_not_cramped_icons(_page):
    _mount(_page, _data(calendars=[
        {"id": "google", "label": "Google Calendar", "status": "unavailable"},
        {"id": "icloud", "label": "iCloud (Apple)", "status": "unavailable"},
        {"id": "caldav", "label": "CalDAV (Outlook, Fastmail…)", "status": "unavailable"}]))
    assert _page.locator(".agcalrow").count() == 0, "the panel is closed until asked for"
    body = _page.locator(".agbody").inner_text()
    assert "no está construido" not in body, "the explanatory paragraph is gone from the calendar itself"
    _page.click(".agcalbtn")
    rows = _page.locator(".agcalrow")
    assert rows.count() == 3
    assert "Google Calendar" in rows.nth(0).inner_text()
    size = _page.evaluate(
        "() => { const r = document.querySelector('.agcalico').getBoundingClientRect(); return [r.width, r.height]; }")
    assert size[0] >= 24 and size[1] >= 24, f"an icon you cannot read is not an icon: {size}"


def test_a_grown_card_is_filled_and_nothing_is_clipped(_page):
    """His first screenshot: the card was small and the words at the bottom were cut. The widget fills its
    frame now and the grid scrolls INSIDE it, so no row can fall under the card's edge."""
    _mount(_page, _data(meetings=[_meet("Dentista", start="10:00", end="11:00")]), card_w=920, card_h=640)
    geo = _page.evaluate(
        """() => { const card = document.querySelector('.hb-win').getBoundingClientRect();
                   const root = document.querySelector('.hb-agenda').getBoundingClientRect();
                   const views = document.querySelector('.agviews').getBoundingClientRect();
                   const body = document.querySelector('.agbody');
                   const sc = document.querySelector('.hb-scroll');
                   return {card, root, views, bodyH: body.getBoundingClientRect().height,
                           inner: getComputedStyle(body).overflowY,
                           outer: getComputedStyle(sc).overflowY}; }""")
    assert geo["root"]["bottom"] <= geo["card"]["bottom"] + 1, "the widget never spills past the card"
    assert geo["views"]["bottom"] <= geo["card"]["bottom"], "the view band stays visible"
    assert geo["bodyH"] > 380, "the calendar takes the spare space instead of leaving it empty"
    assert geo["inner"] == "auto" and geo["outer"] == "hidden", "the GRID scrolls, not the card"


def test_a_small_card_still_shows_the_toolbar_and_the_views(_page):
    _mount(_page, _data(), card_w=430, card_h=390)
    geo = _page.evaluate(
        """() => { const card = document.querySelector('.hb-win').getBoundingClientRect();
                   const bar = document.querySelector('.agbar').getBoundingClientRect();
                   const views = document.querySelector('.agviews').getBoundingClientRect();
                   return {card, bar, views}; }""")
    assert geo["bar"]["top"] >= geo["card"]["top"]
    assert geo["views"]["bottom"] <= geo["card"]["bottom"], "the four views stay reachable in a small card"


# ── navigation: ‹ Hoy › and the other views ─────────────────────────────────────────────────────────────

def test_the_arrows_move_a_week_and_today_comes_back(_page):
    _mount(_page, _data())
    first = _page.locator(".agrange").inner_text()
    _page.click("[data-nav=next]")
    moved = _page.locator(".agrange").inner_text()
    assert moved != first, "› must move the week"
    _page.click("[data-nav=today]")
    assert _page.locator(".agrange").inner_text() == first, "Hoy comes back to the current week"


def test_the_month_is_a_calendar_grid_and_a_day_click_opens_that_day(_page):
    _mount(_page, _data(meetings=[_meet("Dentista", day=1, start="10:00", end="11:00")]))
    _page.click(".agtab[data-view=month]")
    assert _page.locator(".agmgrid").count() == 1
    assert _page.locator(".agmdow").count() == 7, "a month has its weekday header"
    assert _page.locator(".agmcell").count() >= 28
    assert _page.locator(".agmev").count() == 1, "the appointment shows in its cell"
    _page.click(".agmcell.today")
    assert _page.locator(".agtab.on").get_attribute("data-view") == "day"
    assert _page.locator(".agcol").count() == 1


def test_the_list_view_groups_what_is_coming_by_day(_page):
    _mount(_page, _data(meetings=[
        _meet("Dentista", day=1, start="10:00", end="11:00", attendees=["Ana"], location="Clínica"),
        _meet("Notario", day=3, start="12:00", end="13:00")]))
    _page.click(".agtab[data-view=list]")
    assert _page.locator(".agday").count() == 2, "one block per day with something in it"
    rows = _page.locator(".agrow").all_inner_texts()
    assert any("Dentista" in r and "Clínica" in r for r in rows), rows


def test_an_empty_list_says_so_plainly(_page):
    _mount(_page, _data())
    _page.click(".agtab[data-view=list]")
    assert "No tienes nada apuntado" in _page.locator(".agempty").inner_text()


def test_an_all_day_event_gets_its_own_band(_page):
    _mount(_page, _data(meetings=[{"title": "Viaje a Madrid", "date": _d(1), "allDay": True}]))
    assert _page.locator(".agallday").count() == 1
    assert "Viaje a Madrid" in _page.locator(".agallday").inner_text()
    assert _page.locator(".agallday .agev").count() == 1, "an all-day event never sits in the hour grid"
