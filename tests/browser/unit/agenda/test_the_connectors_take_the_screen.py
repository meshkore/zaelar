# V2-679 (follow-up) — the agenda's connectors, in the shape the operator asked for TWICE: one icon per
# provider in the subheader plus a plug button, and a door into the Google guide. Until 2026-10-04 that door
# was a connectors SCREEN inside the card (list + a step-by-step Google wizard, with the OAuth window opened
# INSIDE the click). That screen was removed with every other widget's connect screen: there is ONE door to
# connect a service, the ⚙ «Conectores» section opened on that connector with its guide
# (`frontend/app/components/ConnectorWizard.js`), reached from a card through `ctx.openConnector(id)`.
#
# RENDERED, every case: what is pinned is that the subheader still shows every provider, that an unbuilt one
# is inert, and that every live control the card keeps — the Google icon, linked or not, and the plug — lands
# on the same door with the same id, connecting nothing by itself and taking over no view of the calendar.
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

_CALS_OFF = [{"id": "google", "label": "Google Calendar", "status": "off"},
             {"id": "icloud", "label": "iCloud (Apple)", "status": "unavailable"},
             {"id": "caldav", "label": "CalDAV (Outlook, Fastmail…)", "status": "unavailable"}]
_CALS_ON = [dict(_CALS_OFF[0], status="connected"), _CALS_OFF[1], _CALS_OFF[2]]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _d(n: int = 0) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + n * 86400))


def _data(**over):
    d = {"date": _d(), "now": "12:00", "mission": "", "plan": {"blocks": [], "focus": []},
         "active": None, "todayIndex": 0, "meetings": [], "projects": [], "view": None,
         "days": [{"date": _d(i), "label": "X", "weekday": "X",
                   "plan": {"blocks": [], "focus": [], "summary": "", "coaching": [], "warnings": []}}
                  for i in range(7)],
         "calendars": list(_CALS_OFF), "warnings": [], "coaching": []}
    d.update(over)
    return d


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


def _mount(page, data):
    """Mount with a recording ctx: actions and the host's `openConnector` door land in `window.__calls`."""
    page.goto(page._hb_origin)
    page.set_content("<div id='w' style='width:900px;height:620px'></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__mod = mod;
             window.__ctx = {
               action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok: true}); },
               openConnector: (cx) => { window.__calls.push(["openConnector", cx]); },
               top: () => {}, running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_url, data])


def _calls(page):
    return page.evaluate("() => window.__calls")


# ── the header: every provider visible, only the built one alive ────────────────────────────────────────

def test_the_subheader_shows_one_icon_per_provider_and_only_google_is_alive(_page):
    _mount(_page, _data())
    icons = _page.locator(".agconnicon")
    assert icons.count() == 3, "three providers, three icons — the operator's own layout"
    assert _page.locator(".agconnicon:not(.off)").count() == 1, "only Google has a connector behind it"
    assert _page.locator(".agconnicon.off[disabled]").count() == 2, \
        "the two we have not built are DIMMED and inert, not silently clickable"
    # An icon nobody can read is the mistake V2-643 already reverted once.
    box = _page.evaluate("() => { const r = document.querySelector('.agconnicon').getBoundingClientRect();"
                         "        return [r.width, r.height]; }")
    assert box[0] >= 24 and box[1] >= 24, box


def test_a_dimmed_provider_fires_absolutely_nothing(_page):
    _mount(_page, _data())
    _page.locator(".agconnicon.off").first.click(force=True)
    assert _page.evaluate("window.__calls.length") == 0
    assert _page.locator(".agconnscreen").count() == 0, "an unbuilt provider opens no screen either"


def test_googles_icon_is_a_door_into_the_one_connectors_section_when_it_is_not_linked(_page):
    _mount(_page, _data())
    _page.locator(".agconnicon:not(.off)").click()
    assert _calls(_page) == [["openConnector", "google"]], "the icon opens the section on Google and connects nothing"
    assert _page.locator(".agconnscreen, .agwstep").count() == 0, "no guide of the card's own any more"


def test_the_plug_button_is_the_same_door(_page):
    """V2-699's plug, kept: it is the card's door to ITS connector, which lives in ⚙ Conectores."""
    _mount(_page, _data())
    assert _page.locator(".agcol").count() == 7, "the week is showing before we ask for anything"
    _page.click(".agcalbtn")
    assert _calls(_page) == [["openConnector", "google"]]
    assert _page.locator(".agcol").count() == 7, "the calendar stays: nothing takes over the content area"
    assert _page.locator(".agtab.on").count() == 1 and _page.locator(".agtab[disabled]").count() == 0, (
        "the views stay lit and clickable — there is no screen of the card's own to go dead for")


def test_a_connected_google_icon_opens_the_same_section_where_disconnecting_lives(_page):
    """Connected or not, the id is the same and the destination is the same: connect, the default calendar's
    account and «Desconectar» are all the section's; the card keeps only its own preference (the default
    calendar picker, when Google has more than one)."""
    _mount(_page, _data(calendars=[dict(c) for c in _CALS_ON]))
    assert _page.locator(".agconnicon.on").count() == 1
    _page.locator(".agconnicon.on").click()
    assert _calls(_page) == [["openConnector", "google"]]
    assert _page.locator(".agcaldefsel").count() == 0, "one calendar: no picker to show"
    _mount(_page, _data(calendars=[dict(c) for c in _CALS_ON], defaultCalendarId="work",
                        googleCalendars=[{"id": "primary", "summary": "Personal"}, {"id": "work", "summary": "Trabajo"}]))
    sel = _page.locator(".agcaldefsel")
    assert sel.count() == 1 and sel.input_value() == "work", "the default-calendar preference is the card's own"


def test_the_card_never_opens_a_consent_window_itself(_page):
    """The OAuth window used to be opened INSIDE the click on the card (V2-679's «ni siquiera funciona»). It is
    the section's click now; a card that still called `window.open` or a `connect` action would be a second
    door, which is exactly what was removed."""
    js = (_ENGINE / "widgets" / "agenda" / "widget.js").read_text(encoding="utf-8")
    body = "\n".join(L for L in js.splitlines() if not L.strip().startswith("//"))
    assert "window.open(" not in body and "ctx.connect(" not in body
    assert 'ctx.action("connect"' not in body and 'ctx.action("disconnect"' not in body
    _mount(_page, _data())
    _page.locator(".agconnicon:not(.off)").click()
    _page.click(".agcalbtn")
    assert all(c[0] == "openConnector" for c in _calls(_page)), _calls(_page)
