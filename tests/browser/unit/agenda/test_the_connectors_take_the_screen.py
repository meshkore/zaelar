# V2-679 (follow-up) — the agenda's connectors, in the shape the operator asked for TWICE. His words, with a
# screenshot of the small floating panel the first build produced: «esto no funciona igual como en los
# mensajes. He dicho que hay un icono, un botón para conectores y luego a la izquierda los tres iconos…
# Si se clica en conectores, todo el espacio central de contenido lo centramos en los conectores, igual que
# en mensajería. Y se desactiva el foco o el botón activo de día, semana, mes y lista… el botón de conectar
# a Google Calendar lo que hace es inicia un wizard con las instrucciones en la zona central del widget…
# también tiene que tener una barrita de navegación para volver atrás… Ahora este botón de conectar a Google
# Calendar ni siquiera funciona.»
#
# RENDERED, every case. The one that matters most cannot be read from the source at all: WHEN the popup is
# opened. `window.open()` called after an `await` is outside the click's user gesture and every mainstream
# browser blocks it in SILENCE — which is exactly the «ni siquiera funciona» he reported — so the check here
# is an ORDERING one: the window has to be opened before the connect action's promise resolves.
from __future__ import annotations

import pathlib
import re
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
#: No Google ACCOUNT registered yet — the only state in which this widget still teaches how to make one.
#: Since V2-685 that app belongs to the Google account and lights six surfaces at once, so an operator who
#: has one (status "off": registered, not linked) is shown the authorisation and nothing else.
_CALS_UNCONF = [dict(_CALS_OFF[0], status="unconfigured"), _CALS_OFF[1], _CALS_OFF[2]]


def _unconf(**over):
    return _data(calendars=[dict(c) for c in _CALS_UNCONF], **over)


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


def _mount(page, data, *, connect=None):
    """Mount with a recording ctx. `connect` decides what the `connect` action answers:
    None = an immediate {ok:True,url:…}; "deferred" = a promise the test resolves by hand (so the ORDER of
    window.open against it can be measured); "error" = the connector's own refusal."""
    page.goto(page._hb_origin)
    page.set_content("<div id='w' style='width:900px;height:620px'></div>")
    page.evaluate(
        """async ([src, data, mode]) => {
             window.__calls = [];
             window.__seq = [];
             window.__opened = [];
             window.open = (url, name) => { window.__seq.push("open"); window.__opened.push([url, name]);
                                            return {location: "", close(){ window.__seq.push("close"); }}; };
             const mod = await import(src);
             window.__mod = mod;
             window.__ctx = {
               action: (n, p) => {
                 window.__calls.push([n, p || {}]);
                 if (n !== "connect") return Promise.resolve({ok: true});
                 if (mode === "error") return Promise.resolve({ok: false, error: "sin app OAuth registrada"});
                 if (mode === "deferred") return new Promise(res => {
                   window.__resolveConnect = () => { window.__seq.push("resolve");
                                                     res({ok: true, url: "https://accounts.google.com/x"}); };
                 });
                 window.__seq.push("resolve");
                 return Promise.resolve({ok: true, url: "https://accounts.google.com/x"});
               },
               top: () => {}, running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_url, data, connect])


def _open_connectors(page, data=None, **kw):
    _mount(page, data or _data(), **kw)
    page.click(".agcalbtn")


def _into_wizard(page, data=None, **kw):
    _open_connectors(page, data, **kw)
    page.click(".agcalbtn2")                      # «Conectar Google Calendar» → the guide


def _to_last_step(page, data=None, **kw):
    """Walk to the step that holds «Conectar Google Calendar», however many come before it — which now
    depends on whether the Google account exists (none when it does, three when it does not).

    The termination condition is «Paso N de N», not «there is a counter»: the widget shows the counter on
    EVERY step of a multi-step guide, the last one included (`if(total > 1)` in renderGoogleWizard), so a
    loop that stops when the counter disappears never stops — it clicks the connect button over and over,
    with no Playwright timeout to end it because every click legitimately succeeds. Measured at 772a569b,
    before this pass touched anything: the run simply hangs. The `range` is a second floor under it — a
    helper that walks a wizard must not be able to hang the suite whatever the widget does next.
    """
    _into_wizard(page, data, **kw)
    for _ in range(8):
        counter = page.locator(".agwcount")
        if not counter.count():
            break                                 # one screen only: it already IS the one that connects
        n, total = (int(x) for x in re.findall(r"\d+", counter.inner_text())[:2])
        if n >= total:
            break
        page.click(".agwfoot .agcalbtn2.hb-btn--primary")


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


def test_googles_icon_is_a_door_into_its_own_guide_when_it_is_not_linked(_page):
    _mount(_page, _data())
    _page.locator(".agconnicon:not(.off)").click()
    assert _page.locator(".agwstep").count() == 1, "an unconnected provider lands on its wizard directly"
    assert _page.evaluate("window.__calls.length") == 0, "opening the guide connects nothing"


# ── the connectors take the WHOLE content area, and the views go dead ───────────────────────────────────

def test_the_connectors_button_takes_over_the_content_area(_page):
    _mount(_page, _data())
    assert _page.locator(".agcol").count() == 7, "the week is showing before we ask for anything"
    _page.click(".agcalbtn")
    assert _page.locator(".agconnscreen").count() == 1
    assert _page.locator(".agcol").count() == 0, "the calendar is REPLACED, not covered by a floating panel"
    assert _page.locator(".agcalrow").count() == 3, "every provider gets its own labelled row"
    # It fills the content area instead of being a 360px card floating in the middle of it.
    width = _page.evaluate("""() => { const s = document.querySelector('.agconnscreen').getBoundingClientRect();
                                      const b = document.querySelector('.agbody').getBoundingClientRect();
                                      return [s.width, b.width]; }""")
    assert width[0] > width[1] * 0.6, f"the connectors screen has to use the content area: {width}"


def test_while_the_connectors_are_showing_no_view_is_active_and_none_can_be_clicked(_page):
    _open_connectors(_page)
    assert _page.locator(".agtab.on").count() == 0, "no day/week/month/list is the one on screen any more"
    assert _page.locator(".agtab[disabled]").count() == 4, "and none of them is clickable while we are here"


def test_going_back_returns_to_the_very_view_he_was_reading(_page):
    _mount(_page, _data())
    _page.click(".agtab[data-view='month']")
    assert _page.locator(".agmgrid").count() == 1
    _page.click(".agcalbtn")
    _page.click(".agconnback")                    # «← Agenda»
    assert _page.locator(".agconnscreen").count() == 0
    assert _page.locator(".agtab.on").get_attribute("data-view") == "month", \
        "the view survives underneath the setup screen"


def test_a_pushed_voice_view_leaves_the_connectors_screen(_page):
    _open_connectors(_page)
    _page.evaluate("d => window.__mod.render(document.getElementById('w'), d, window.__ctx)",
                   _data(view={"sel": "month", "n": 1}))
    assert _page.locator(".agconnscreen").count() == 0, \
        "a navigation order must not render underneath a setup screen (V2-626's lesson)"
    assert _page.locator(".agmgrid").count() == 1


# ── the wizard: instructions in the content area, with a way back at every step ─────────────────────────

def test_connect_starts_the_GUIDE_and_does_not_fire_a_handshake_that_cannot_work(_page):
    _open_connectors(_page, _unconf())
    _page.click(".agcalbtn2")
    assert _page.locator(".agwstep").count() == 1
    assert _page.evaluate("window.__calls.length") == 0, \
        "the operator's rule: this button starts the wizard, it does not connect"
    assert "1" in _page.locator(".agwcount").inner_text()


def test_an_operator_who_ALREADY_has_a_google_account_is_shown_only_the_authorisation(_page):
    """The complaint that opened this pass: «parece la versión anterior que no la has limpiado».

    Until V2-685 every operator got the same four steps — create a Google Cloud project, create an OAuth
    client, paste it into ⚙ — teaching them to register an app for the CALENDAR. That app now belongs to
    the Google ACCOUNT and registering it once lights Gmail, Calendar, Meet, Drive, Photos and YouTube
    together. For anyone who has it, those three steps are work already done by somebody else, and showing
    them is the previous generation's flow.
    """
    _open_connectors(_page)                       # status "off": the app IS registered, just not linked
    _page.click(".agcalbtn2")
    assert _page.locator(".agwstep").count() == 1
    assert _page.locator(".agwcount").count() == 0, "one screen is not «Paso 1 de N»"
    assert _page.locator(".agwlink").count() == 0, "and it does not re-teach the Google Cloud console"
    assert _page.evaluate("window.__calls.length") == 0, "opening it still connects nothing"
    primary = _page.locator(".agwfoot .agcalbtn2.hb-btn--primary").inner_text()
    assert "Google" in primary, f"the one screen is the one with the button: {primary!r}"


def test_the_guide_walks_one_step_at_a_time_and_every_step_can_go_back(_page):
    _into_wizard(_page, _unconf())
    seen = []
    for _ in range(3):
        seen.append(_page.locator(".agwtitle").inner_text())
        assert _page.locator(".agwstep").count() == 1, "one step at a time, never a stack of boxes"
        _page.click(".agwfoot .agcalbtn2.hb-btn--primary")
    assert len(set(seen)) == 3, f"each step says something of its own: {seen}"
    # Back walks the same path in reverse, and from step 1 it lands on the connector list — never outside.
    for _ in range(3):
        _page.click(".agwfoot .agcalbtn2.hb-btn--secondary")
    assert _page.locator(".agwstep").count() == 1 and _page.locator(".agwcount").inner_text().count("1") >= 1
    _page.click(".agwfoot .agcalbtn2.hb-btn--secondary")
    assert _page.locator(".agcalrow").count() == 3, "back from the first step returns to the connector list"


def test_the_guide_opens_the_real_google_pages_it_talks_about(_page):
    _into_wizard(_page, _unconf())
    hrefs = _page.locator(".agwlink").evaluate_all("els => els.map(e => e.href)")
    assert hrefs and all(h.startswith("https://console.cloud.google.com/") for h in hrefs), hrefs
    assert all(_page.locator(".agwlink").nth(i).get_attribute("target") == "_blank"
               for i in range(len(hrefs))), "a step's page opens beside the agenda, never over it"


def test_the_breadcrumb_says_where_back_goes(_page):
    _into_wizard(_page)
    assert "Google Calendar" in _page.locator(".agwcur").inner_text()
    _page.click(".agwcrumb .agconnback")
    assert _page.locator(".agcalrow").count() == 3


# ── the last step is the only one that connects — and it has to actually work ───────────────────────────

def test_only_the_last_step_asks_google_for_permission(_page):
    _to_last_step(_page, data=_unconf())
    assert _page.evaluate("window.__calls.length") == 0, "three steps of instructions ask nobody for anything"
    _page.click(".agwfoot .agcalbtn2.hb-btn--primary")
    _page.wait_for_timeout(50)
    call = _page.evaluate("window.__calls.pop()")
    assert call[0] == "connect" and call[1]["provider"] == "google", call
    assert _page.evaluate("window.__opened.length") == 1, "the consent window is opened"


def test_the_window_is_opened_INSIDE_the_click_not_after_the_answer_comes_back(_page):
    """THE defect he reported («ni siquiera funciona»). A popup opened after an `await` has lost the click's
    user activation and is blocked with no error anywhere — so the order is the product, not a detail."""
    _to_last_step(_page, connect="deferred")
    _page.click(".agwfoot .agcalbtn2.hb-btn--primary")
    _page.wait_for_timeout(50)
    assert _page.evaluate("window.__seq") == ["open"], \
        "the window must already be open while the connect action is still in flight"
    _page.evaluate("window.__resolveConnect()")
    _page.wait_for_timeout(50)
    assert _page.evaluate("window.__seq") == ["open", "resolve"]
    assert _page.evaluate("window.__opened[0][0]") == "", "it is opened blank and then navigated"


def test_a_refusal_SAYS_why_instead_of_leaving_the_button_looking_broken(_page):
    _to_last_step(_page, connect="error")
    _page.click(".agwfoot .agcalbtn2.hb-btn--primary")
    _page.wait_for_timeout(50)
    assert "OAuth" in _page.locator(".agwerr").inner_text(), _page.locator(".agwerr").inner_text()
    assert "close" in _page.evaluate("window.__seq"), "the blank window is closed again, not left hanging"


# ── a CONNECTED account: the list screen is where its controls live ─────────────────────────────────────

def test_a_connected_google_offers_its_default_calendar_and_the_way_out(_page):
    data = _data(calendars=[{"id": "google", "label": "Google Calendar", "status": "connected"},
                            {"id": "icloud", "label": "iCloud (Apple)", "status": "unavailable"},
                            {"id": "caldav", "label": "CalDAV", "status": "unavailable"}],
                 googleCalendars=[{"id": "a@g", "summary": "Personal", "backgroundColor": "#123456"},
                                  {"id": "b@g", "summary": "Trabajo", "backgroundColor": "#654321"}],
                 defaultCalendarId="a@g")
    _open_connectors(_page, data)
    assert _page.locator(".agcalst.on").count() == 1
    rows = _page.locator(".agcaldefrow")
    assert rows.count() == 2, "every Google calendar can be the one new appointments land in"
    assert _page.evaluate("() => document.querySelectorAll('.agcaldefrow input')[0].checked") is True
    rows.nth(1).click()
    call = _page.evaluate("window.__calls.pop()")
    assert call[0] == "set_default_calendar" and call[1]["calendarId"] == "b@g", call
    _page.click(".agcalbtn2.hb-btn--danger")
    assert _page.evaluate("window.__calls.pop()")[0] == "disconnect"


def test_a_connected_google_icon_opens_the_list_and_never_the_guide(_page):
    data = _data(calendars=[{"id": "google", "label": "Google Calendar", "status": "connected"},
                            {"id": "icloud", "label": "iCloud", "status": "unavailable"},
                            {"id": "caldav", "label": "CalDAV", "status": "unavailable"}])
    _mount(_page, data)
    _page.locator(".agconnicon.on").click()
    assert _page.locator(".agcalrow").count() == 3
    assert _page.locator(".agwstep").count() == 0, "there is nothing to guide once the account is linked"


# ── V2-686: the voice can ask to connect, and it lands ON the button ────────────────────────────────────
# Measured live on 2026-09-14 (`T14·76b6`): «open the google connector in the agenda widget» executed
# `agenda:connect`, the action returned a good consent URL, and the screen did not move. The voice cannot
# finish the OAuth — the popup only survives inside the click, which is what
# `test_the_window_is_opened_INSIDE_the_click…` measures a few lines above — so it does the half it can:
# it leaves the operator in front of the button. RENDERED, because the jump belongs to `render`, not `data`.

def test_a_pushed_voice_connect_lands_on_the_step_that_has_the_button(_page):
    _mount(_page, _data(connect={"n": 1, "at": 9e9}))
    assert _page.locator(".agwstep").count() == 1, "the voice order did not open the guide"
    assert _page.locator(".agwfoot .agcalbtn2.hb-btn--primary").inner_text().strip() != "", "no button to press"
    assert _page.locator(".agwcount").count() == 0, \
        "with the account already registered there is ONE screen, and it is the one with the button"
    assert _page.evaluate("window.__calls.length") == 0, \
        "the voice CANNOT ask Google for the permission: that belongs to the operator's click"


def test_the_pushed_connect_does_not_reopen_itself_on_every_repaint(_page):
    """Same token: a repaint (an agenda tick, an SSE push) must not drag him back to a screen he has just
    left. Same contract as the pushed view above."""
    _mount(_page, _data(connect={"n": 1, "at": 9e9}))
    _page.click(".agwfoot .agcalbtn2.hb-btn--secondary")                    # «Atrás» -> out of the guide
    _page.click(".agcalbtn")                                   # and close the connectors screen
    _page.evaluate("d => window.__mod.render(document.getElementById('w'), d, window.__ctx)",
                   _data(connect={"n": 1, "at": 9e9}))
    assert _page.locator(".agwstep").count() == 0, "a repaint put the connect screen back on top of him"


def test_asking_a_SECOND_time_brings_the_button_back(_page):
    """And the other half: if the Google window closed on him and he asks again, it has to jump again."""
    _mount(_page, _data(connect={"n": 1, "at": 9e9}))
    _page.click(".agwfoot .agcalbtn2.hb-btn--secondary")
    _page.click(".agcalbtn")
    _page.evaluate("d => window.__mod.render(document.getElementById('w'), d, window.__ctx)",
                   _data(connect={"n": 2, "at": 9e9}))
    assert _page.locator(".agwstep").count() == 1
