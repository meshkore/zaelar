"""V2-540 — the agenda RENDERED: a view that voice can move, and the calendar connectors in its header.

The defect this file exists to catch was reported by the operator against his own live session: he asked the
agenda to show TOMORROW, it replied «Te abro la agenda con la vista de mañana» — and stayed on today. The
observability of that session (events 873 / 931 / 995, 2026-09-01 15:11) shows exactly one thing firing each
time: a bare `show:agenda`, which opens on today. The day tabs were pure DOM state with no name in the manifest,
so there was no wrong tool to pick — there was NO tool, and an undeclared capability is one the model narrates.

Rendering is the only way to check it. Whether a pushed view actually MOVES the selected tab, and whether it
declines to move on a plain refresh, are questions about a mounted widget's state — reading widget.js would only
prove the code was written.
"""
from __future__ import annotations

import asyncio
import os

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "agenda", "widget.js")

_TODAY = "2026-09-01"
_DAYS = [
    {"date": "2026-09-01", "label": "Hoy", "weekday": "Lun", "plan": {"summary": "día de hoy", "blocks": []}},
    {"date": "2026-09-02", "label": "Mañana", "weekday": "Mar",
     "plan": {"summary": "día de mañana", "blocks": [],
              "meetings": [{"title": "Traumatólogo", "startTime": "08:00"}]}},
    {"date": "2026-09-03", "label": "Jue", "weekday": "Jue", "plan": {"summary": "jueves", "blocks": []}},
]
_BASE = {
    "date": _TODAY, "now": "15:11", "mission": "",
    "plan": _DAYS[0]["plan"], "active": None,
    "days": _DAYS, "todayIndex": 0,
    "meetings": [{"title": "Traumatólogo", "date": "2026-09-02", "startTime": "08:00"}],
    "projects": [], "warnings": [], "coaching": [],
    "calendars": [{"id": "google", "label": "Google Calendar", "status": "unavailable"},
                  {"id": "icloud", "label": "iCloud (Apple)", "status": "unavailable"},
                  {"id": "caldav", "label": "CalDAV (Outlook, Fastmail…)", "status": "unavailable"}],
}

_HTML = """<!doctype html><html data-theme="dark"><head><meta charset="utf-8"><style>
:root{--hb-bg:#0f1720;--hb-ink:#e8eef6;--hb-muted:#9fb0c4;--hb-muted-2:#6f8299;
      --hb-line:#243244;--hb-accent:#2F6FEB;--hb-accent2:#16B8A6;--hb-neutral:#c2ccda}
body{margin:0;background:#0a1017}#host{width:720px}
</style></head><body><div id="host"></div></body></html>"""

_MEASURE = """() => {
  const el = document.querySelector('.hb-agenda');
  if (!el) return {mounted: false};
  const tabs = [...el.querySelectorAll('.agtab')];
  const on = tabs.find(t => t.classList.contains('on'));
  const icons = [...el.querySelectorAll('.calicon')];
  return {
    mounted: true,
    tabs: tabs.map(t => t.textContent),
    selected: on ? on.textContent : null,
    week_view: !!el.querySelector('.agwday'),
    month_view: !!el.querySelector('.agmonth'),
    month_label: (el.querySelector('.agmnav b') || {}).textContent || '',
    cal_count: icons.length,
    cal_titles: icons.map(i => i.title),
    cal_svgs: icons.filter(i => i.querySelector('svg path')).length,
    cal_lit: icons.filter(i => i.classList.contains('on')).length,
    cal_in_header: icons.every(i => !!i.closest('.hd')),
    note: (el.querySelector('.calnote') || {}).textContent || '',
  };
}"""


def _run(steps):
    """Paint once, then apply each `data` in `steps` through the SAME element — the way a live refresh does,
    which is the only way the 'does not move on a plain refresh' half can be observed at all."""
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 760, "height": 900})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))

            async def _page(route):
                await route.fulfill(status=200, content_type="text/html", body=_HTML)
            await pg.route("http://zaelar.test/", _page)
            await pg.goto("http://zaelar.test/")
            src = open(_WIDGET, encoding="utf-8").read()
            await pg.add_script_tag(
                content=src.replace("export function render", "window.render = function render"))
            out = []
            for data in steps:
                await pg.evaluate(
                    "d => window.render(document.getElementById('host'), d, {action: async () => ({})})", data)
                await pg.wait_for_timeout(60)
                m = await pg.evaluate(_MEASURE)
                m["errors"] = errors
                out.append(m)
            await b.close()
            return out
    return asyncio.run(go())


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


@pytest.fixture(scope="module")
def plain(playwright_available):
    return _run([_BASE])[0]


def test_it_mounts_on_today_without_a_single_error(plain):
    assert plain["mounted"], "the agenda did not paint"
    assert plain["errors"] == [], plain["errors"]
    assert plain["selected"] == "Hoy", plain["selected"]


def test_a_pushed_view_MOVES_the_day_that_is_on_screen(playwright_available):
    """THE defect. `show_day` with tomorrow's date has to land on the «Mañana» tab — opening the widget again
    never could, because showing it always opens on today."""
    before, after = _run([_BASE, {**_BASE, "view": {"sel": "2026-09-02", "n": 1}}])
    assert before["selected"] == "Hoy", before["selected"]
    assert after["selected"] == "Mañana", after["selected"]


def test_a_plain_refresh_does_NOT_yank_the_day_the_operator_is_reading(playwright_available):
    """The other half, and the reason the push carries a counter instead of just a day: once applied, the same
    view arriving again on every data refresh must leave his own tab alone."""
    steps = _run([_BASE,
                  {**_BASE, "view": {"sel": "2026-09-02", "n": 1}},   # voice: tomorrow
                  {**_BASE, "view": {"sel": "2026-09-02", "n": 1}}])  # a refresh carrying the same token
    assert steps[1]["selected"] == "Mañana"
    assert steps[2]["selected"] == "Mañana", "the refresh must not re-apply, but must not undo it either"


def test_asking_for_the_SAME_day_twice_still_lands(playwright_available):
    """Why the token is a counter and not the day: tomorrow → he clicks back to today → «mañana» again. With
    the day as the token that second ask would write an identical value and move nothing, which is this very
    bug wearing another mask."""
    steps = _run([_BASE,
                  {**_BASE, "view": {"sel": "2026-09-02", "n": 1}},
                  {**_BASE, "view": {"sel": "2026-09-01", "n": 2}},
                  {**_BASE, "view": {"sel": "2026-09-02", "n": 3}}])
    assert [s["selected"] for s in steps] == ["Hoy", "Mañana", "Hoy", "Mañana"]


def test_week_and_month_are_reachable_by_voice_too(playwright_available):
    # Two SEPARATE runs on purpose: within one element the second push carries the same token as the first and
    # is correctly ignored, which is the counter working, not the view failing.
    wk = _run([{**_BASE, "view": {"sel": "week", "n": 1}}])[0]
    mo = _run([{**_BASE, "view": {"sel": "month", "n": 1}}])[0]
    assert wk["week_view"], "«ponme la semana» must reach the week overview"
    assert mo["month_view"], "«vista de mes» must reach the calendar"


def test_a_date_beyond_the_horizon_opens_its_MONTH_instead_of_lying(playwright_available):
    """The horizon is today..+6, so «el 20 de octubre» has no tab. Landing silently on today would be the same
    lie the action exists to kill; the month view can reach any date, so it goes there — pointed at October."""
    m = _run([{**_BASE, "view": {"sel": "2026-10-20", "n": 1}}])[0]
    assert m["month_view"], "a far date must open the month view"
    assert "Octubre" in m["month_label"] or "octubre" in m["month_label"], m["month_label"]


def test_the_calendar_connectors_are_in_the_header_with_real_logos(plain):
    """The operator's second ask: the connectors visible up top, like messaging's channels. Real inline <path>
    logos — a widget that pulled them from a CDN would be a blank strip offline."""
    assert plain["cal_count"] == 3, plain["cal_count"]
    assert plain["cal_in_header"], "the strip must live in the header, not floating in the body"
    assert plain["cal_svgs"] == 3, "each provider needs its own drawn logo, not a letter"


def test_the_strip_tells_the_TRUTH_that_none_is_built_yet(plain):
    """`connectors/` holds six connectors and not one is a calendar. Every icon must read as not linked, and
    saying WHY out loud is deliberate (INI-027: the wishlist is public)."""
    # The presence assertion is not decoration: without it, a strip that painted NOTHING would satisfy both
    # lines below vacuously (`all([])` is True) and this test would guard an empty header.
    assert plain["cal_count"] == 3, plain["cal_count"]
    assert plain["cal_lit"] == 0, "nothing may look connected while no calendar connector exists"
    assert all("todavía no disponible" in t for t in plain["cal_titles"]), plain["cal_titles"]


def test_clicking_a_provider_explains_where_the_appointments_actually_live(playwright_available):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 760, "height": 900})

            async def _page(route):
                await route.fulfill(status=200, content_type="text/html", body=_HTML)
            await pg.route("http://zaelar.test/", _page)
            await pg.goto("http://zaelar.test/")
            src = open(_WIDGET, encoding="utf-8").read()
            await pg.add_script_tag(
                content=src.replace("export function render", "window.render = function render"))
            await pg.evaluate(
                "d => window.render(document.getElementById('host'), d, {action: async () => ({})})", _BASE)
            await pg.click(".calicon")
            await pg.wait_for_timeout(60)
            m = await pg.evaluate(_MEASURE)
            await b.close()
            return m
    m = go and asyncio.run(go())
    assert "Google Calendar" in m["note"], m["note"]
    assert "no está construido" in m["note"], m["note"]


def test_a_view_pushed_a_moment_ago_is_honoured_by_a_FRESHLY_mounted_widget(playwright_available):
    """`show_day` writes, then `show_widget` opens the card: its very first paint has to arrive already on
    tomorrow, because opening the widget can never select a day by itself. Staleness is handled where the clock
    is (`data.py::_fresh_view`) — by the time a push is old, `view` is simply not in the payload any more."""
    m = _run([{**_BASE, "view": {"sel": "2026-09-02", "n": 1}}])[0]
    assert m["selected"] == "Mañana", m["selected"]


def test_no_pushed_view_means_TODAY_and_nothing_moves(playwright_available):
    """The expired case as the widget actually sees it: no `view` key at all."""
    m = _run([_BASE])[0]
    assert m["selected"] == "Hoy", m["selected"]
