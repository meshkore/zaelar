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
from tests.browser import widget_client

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

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
  const icons = [...el.querySelectorAll('.agconnicon')];
  return {
    mounted: true,
    tabs: tabs.map(t => t.textContent),
    view: on ? on.dataset.view : null,
    range: (el.querySelector('.agrange') || {}).textContent || '',
    day_columns: el.querySelectorAll('.agcol').length,
    today_marked: !!el.querySelector('.agdh.today, .agmcell.today, .agday.today'),
    month_view: !!el.querySelector('.agmgrid'),
    list_view: !!el.querySelector('.aglist'),
    // The connector icons beside the plug (2026-10-04: the card's door to ⚙ Conectores, no panel of its own).
    icon_count: icons.length,
    icon_titles: icons.map(b => b.title),
    icon_svgs: icons.filter(b => b.querySelector('svg path')).length,
    icon_doors: icons.filter(b => !b.disabled).length,
    icon_lit: icons.filter(b => b.classList.contains('on')).length,
    in_card_panel: el.querySelectorAll('.agpanel, .agcalrow').length,
    plug: el.querySelectorAll('.agcalbtn').length,
    opened: (window.__cx || []).slice(),
  };
}"""


_RENDER = """([d, lang]) => { window.__cx = window.__cx || [];
  window.render(document.getElementById('host'), d,
                {action: async () => ({}), lang, openConnector: id => window.__cx.push(id)}); }"""


def _run(steps, lang="es", clicks=()):
    """Paint once, then apply each `data` in `steps` through the SAME element — the way a live refresh does,
    which is the only way the 'does not move on a plain refresh' half can be observed at all. `lang` is the
    host's `ctx.lang` (the card shapes dates with it); `clicks` are selectors clicked after the LAST step."""
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
            await widget_client.mount(pg, "agenda")
            out = []
            for i, data in enumerate(steps):
                await pg.evaluate(_RENDER, [data, lang])
                await pg.wait_for_timeout(60)
                if i == len(steps) - 1:
                    for sel in clicks:
                        await pg.click(sel, force=True)
                        await pg.wait_for_timeout(40)
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


@pytest.mark.parametrize("lang,month", [("es", "octubre"), ("en", "october")])
def test_a_date_beyond_the_horizon_lands_on_THAT_date_instead_of_lying(playwright_available, lang, month):
    """The horizon is today..+6, so «el 20 de octubre» used to have no tab and was redirected to its month.
    Since V2-643 a day view can show ANY date (meetings arrive for all of them), so it simply goes there.
    What must never happen — landing silently on today — is what this checks. The range is written in the
    language the HOST passes (`ctx.lang`), so it is checked in two of them."""
    m = _run([{**_BASE, "view": {"sel": "2026-10-20", "n": 1}}], lang=lang)[0]
    assert m["view"] == "day", m
    assert "20" in m["range"] and month in m["range"].lower(), m["range"]


def test_every_calendar_provider_is_a_drawn_logo_named_in_its_tooltip(playwright_available):
    """The operator's V2-643 complaint: «no se sabe qué significa ninguno». One icon per provider the data
    names, each a real inline <path> logo (a CDN logo is a blank strip offline) and each naming its provider."""
    m = _run([_BASE])[0]
    assert m["icon_count"] == 3, m
    assert m["icon_svgs"] == 3, "each provider needs its own drawn logo, not a letter"
    for c, title in zip(_BASE["calendars"], m["icon_titles"]):
        assert title.startswith(c["label"]), (c["label"], title)


def test_only_a_built_connector_is_a_door_and_nothing_looks_linked_that_is_not(playwright_available):
    """Google is the only calendar with a connector behind it: its icon is the one live control, iCloud and
    CalDAV are visible and inert. Nothing reads as linked while the data says nothing is — and the same icon
    DOES light once Google is connected, so the zero below is a measurement and not a dead selector."""
    off = _run([_BASE])[0]
    assert off["icon_doors"] == 1, "only the built connector may be clickable"
    assert off["icon_lit"] == 0, "nothing may look connected while no calendar is linked"
    linked = {**_BASE, "calendars": [{**_BASE["calendars"][0], "status": "connected"}] + _BASE["calendars"][1:]}
    assert _run([linked])[0]["icon_lit"] == 1, "a linked Google has to read as linked"


def test_the_plug_and_the_google_icon_open_the_google_connector_in_settings(playwright_available):
    """Since 2026-10-04 linking lives in ONE place, ⚙ Conectores, and the card only opens it (`ctx.openConnector`)
    on ITS connector — the voice and the buttons share that door. So: the plug and the Google icon each open
    `google`, an inert provider opens nothing, and the card never draws a connect panel of its own."""
    m = _run([_BASE], clicks=[".agcalbtn", ".agconnicon:nth-child(1)", ".agconnicon:nth-child(2)"])[0]
    assert m["plug"] == 1, m
    assert m["opened"] == ["google", "google"], m["opened"]
    assert m["in_card_panel"] == 0, "the card draws no connect panel of its own — that is ⚙ Conectores' job"
    assert m["errors"] == [], m["errors"]


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
