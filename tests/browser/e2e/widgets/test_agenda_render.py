"""V2-540 — the agenda RENDERED: a view that voice can move, and the calendar connectors it does not lie about.

⚠️ REWRITTEN for V2-643 (2026-09-09), which replaced the per-day tab strip with the classic calendar shapes
(Día · Semana · Mes · Lista + ‹ Hoy ›) after the operator's redesign order. Every behavioural claim below is
the SAME one this file was written for — a pushed view lands, a plain refresh does not yank it, asking twice
still lands, a far date is not silently swallowed, and the connectors tell the truth about being unbuilt —
only WHERE they are read from moved: the day that is on screen is now the toolbar's range, not a lit tab,
and the connectors live in their own panel instead of three cramped icons in the header.

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
  const rows = [...el.querySelectorAll('.agcalrow')];
  return {
    mounted: true,
    tabs: tabs.map(t => t.textContent),
    view: on ? on.dataset.view : null,
    range: (el.querySelector('.agrange') || {}).textContent || '',
    day_columns: el.querySelectorAll('.agcol').length,
    today_marked: !!el.querySelector('.agdh.today, .agmcell.today, .agday.today'),
    month_view: !!el.querySelector('.agmgrid'),
    list_view: !!el.querySelector('.aglist'),
    cal_count: rows.length,
    cal_names: rows.map(r => (r.querySelector('.agcalname') || {}).textContent || ''),
    cal_states: rows.map(r => (r.querySelector('.agcalst') || {}).textContent || ''),
    cal_svgs: rows.filter(r => r.querySelector('.agcalico svg path')).length,
    cal_lit: rows.filter(r => (r.querySelector('.agcalst') || {classList:{contains:()=>false}})
                                .classList.contains('on')).length,
    note: (el.querySelector('.agpanel .agnote') || {}).textContent || '',
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


def test_it_mounts_on_the_current_week_without_a_single_error(plain):
    assert plain["mounted"], "the agenda did not paint"
    assert plain["errors"] == [], plain["errors"]
    assert plain["view"] == "week", plain["view"]
    assert plain["day_columns"] == 7, "the week is SEVEN columns, one per day (the operator's spec)"


def test_a_pushed_view_MOVES_the_day_that_is_on_screen(playwright_available):
    """THE defect. `show_day` with tomorrow's date has to land ON tomorrow — opening the widget again never
    could, because showing it always opens on today."""
    before, after = _run([_BASE, {**_BASE, "view": {"sel": "2026-09-02", "n": 1}}])
    assert before["view"] == "week", before["view"]
    assert after["view"] == "day" and after["day_columns"] == 1, after
    assert "2" in after["range"], after["range"]


def test_a_plain_refresh_does_NOT_yank_the_day_the_operator_is_reading(playwright_available):
    """The other half, and the reason the push carries a counter instead of just a day: once applied, the same
    view arriving again on every data refresh must leave his own tab alone."""
    steps = _run([_BASE,
                  {**_BASE, "view": {"sel": "2026-09-02", "n": 1}},   # voice: tomorrow
                  {**_BASE, "view": {"sel": "2026-09-02", "n": 1}}])  # a refresh carrying the same token
    assert steps[1]["range"] == steps[2]["range"], "the refresh must not undo the day he was left on"
    assert steps[1]["view"] == steps[2]["view"] == "day"


def test_asking_for_the_SAME_day_twice_still_lands(playwright_available):
    """Why the token is a counter and not the day: tomorrow → he clicks back to today → «mañana» again. With
    the day as the token that second ask would write an identical value and move nothing, which is this very
    bug wearing another mask."""
    steps = _run([_BASE,
                  {**_BASE, "view": {"sel": "2026-09-02", "n": 1}},
                  {**_BASE, "view": {"sel": "2026-09-01", "n": 2}},
                  {**_BASE, "view": {"sel": "2026-09-02", "n": 3}}])
    ranges = [s["range"] for s in steps]
    assert ranges[1] != ranges[2], "the second push moved back to today"
    assert ranges[1] == ranges[3], "asking for the same day again lands, because the token is a COUNTER"


def test_week_and_month_are_reachable_by_voice_too(playwright_available):
    # Two SEPARATE runs on purpose: within one element the second push carries the same token as the first and
    # is correctly ignored, which is the counter working, not the view failing.
    wk = _run([{**_BASE, "view": {"sel": "week", "n": 1}}])[0]
    mo = _run([{**_BASE, "view": {"sel": "month", "n": 1}}])[0]
    li = _run([{**_BASE, "view": {"sel": "list", "n": 1}}])[0]
    assert wk["view"] == "week" and wk["day_columns"] == 7, wk
    assert mo["month_view"], "«vista de mes» must reach the calendar"
    assert li["list_view"], "«la lista» must reach the Schedule view (V2-643)"


def test_a_date_beyond_the_horizon_lands_on_THAT_date_instead_of_lying(playwright_available):
    """The horizon is today..+6, so «el 20 de octubre» used to have no tab and was redirected to its month.
    Since V2-643 a day view can show ANY date (meetings arrive for all of them), so it simply goes there.
    What must never happen — landing silently on today — is what this checks."""
    m = _run([{**_BASE, "view": {"sel": "2026-10-20", "n": 1}}])[0]
    assert m["view"] == "day", m
    assert "20" in m["range"] and ("octubre" in m["range"].lower()), m["range"]


def test_the_calendar_connectors_are_readable_rows_with_real_logos(playwright_available):
    """The operator's V2-643 complaint about the old strip: «los iconos son tan pequeños y están apelmazados
    que no se sabe qué significa ninguno». They live in their own panel now, one labelled row each, still with
    real inline <path> logos — a widget that pulled them from a CDN would be a blank strip offline."""
    m = _open_calendars()
    assert m["cal_count"] == 3, m["cal_count"]
    assert m["cal_svgs"] == 3, "each provider needs its own drawn logo, not a letter"
    assert all(n.strip() for n in m["cal_names"]), "every row NAMES its provider"


def test_the_panel_tells_the_TRUTH_that_none_is_built_yet(playwright_available):
    """`connectors/` holds six connectors and not one is a calendar. Every row must read as not linked, and
    saying WHY out loud is deliberate (INI-027: the wishlist is public)."""
    m = _open_calendars()
    # The presence assertion is not decoration: without it, a panel that painted NOTHING would satisfy both
    # lines below vacuously (`all([])` is True) and this test would guard an empty screen.
    assert m["cal_count"] == 3, m["cal_count"]
    assert m["cal_lit"] == 0, "nothing may look connected while no calendar connector exists"
    assert all("disponible" in t for t in m["cal_states"]), m["cal_states"]


def _open_calendars():
    """Paint, then open the calendars panel — where the connectors live since V2-643."""
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
            await pg.click(".agcalbtn")
            await pg.wait_for_timeout(60)
            m = await pg.evaluate(_MEASURE)
            await b.close()
            return m
    return asyncio.run(go())


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
            await pg.click(".agcalbtn")
            await pg.wait_for_timeout(60)
            m = await pg.evaluate(_MEASURE)
            await b.close()
            return m
    m = go and asyncio.run(go())
    assert "Google Calendar" in " ".join(m["cal_names"]), m["cal_names"]
    assert "Zaelar" in m["note"], m["note"]


def test_a_view_pushed_a_moment_ago_is_honoured_by_a_FRESHLY_mounted_widget(playwright_available):
    """`show_day` writes, then `show_widget` opens the card: its very first paint has to arrive already on
    tomorrow, because opening the widget can never select a day by itself. Staleness is handled where the clock
    is (`data.py::_fresh_view`) — by the time a push is old, `view` is simply not in the payload any more."""
    m = _run([{**_BASE, "view": {"sel": "2026-09-02", "n": 1}}])[0]
    assert m["view"] == "day" and "2" in m["range"], m


def test_no_pushed_view_means_TODAY_and_nothing_moves(playwright_available):
    """The expired case as the widget actually sees it: no `view` key at all — the current week, with today
    in it, and nothing pulled anywhere else."""
    m = _run([_BASE])[0]
    assert m["view"] == "week", m["view"]
    # The fixture's today is Tue 2026-09-01, so the week it belongs to is 31 aug – 6 sep: what must be true
    # is that TODAY is the day on screen, not that the range starts on it (a week view never does).
    assert m["today_marked"], "today has to be marked inside the week that is showing"
    assert "2026" in m["range"] and "6" in m["range"], m["range"]
