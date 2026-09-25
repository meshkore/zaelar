"""V2-770 — rendered: «ábreme la cita del piano» puts that appointment's card on screen, on its day, and
«cierra la ficha» takes it away without moving anything else.

The data is the product's own `view_data()` after real `open_meeting` / `close_meeting` calls; the card is the
real `widget.js`, re-rendered with each new payload exactly as the canvas does when the store changes.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import socket
import subprocess
import sys

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from tests.waiting import until_sync  # noqa: E402

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
_ES = json.loads((_ENGINE / "i18n/bundles/es.json").read_text())
TODAY = dt.date.today()
TUE = TODAY + dt.timedelta(days=(1 - TODAY.weekday()) % 7 or 7)
WK3 = TUE + dt.timedelta(weeks=2)


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), 0.2).close()
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
def views():
    """Three payloads in the order the canvas would receive them: plain, after «open», after «close»."""
    from widgets.agenda import data as agenda, gcal
    real_svc = gcal.svc
    gcal.svc = lambda: None
    try:
        agenda.apply_action("clear_all", {})
        agenda.apply_action("add_meeting", {
            "title": "Piano de Abril", "date": TUE.isoformat(), "startTime": "15:15", "endTime": "16:00",
            "repeat": "weekly", "until": (TUE + dt.timedelta(weeks=10)).isoformat()})
        plain = agenda.view_data()
        opened = agenda.apply_action("open_meeting", {"title": "piano", "date": WK3.isoformat()})
        closed = agenda.apply_action("close_meeting", {})
        yield plain, opened, closed
        agenda.apply_action("clear_all", {})
    finally:
        gcal.svc = real_svc


@pytest.fixture(scope="module")
def page(views):
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            pg = browser.new_page(viewport={"width": 1100, "height": 800})
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{port}/widgets/agenda/")
            pg.set_content("<div id='w' style='width:900px;height:700px'></div>")
            pg.evaluate("""async ([src, bundle]) => {
                const mod = await import(src);
                window.__ctx = { action: () => Promise.resolve(null), top: () => {}, running: true, lang: "es",
                  t: (k, p) => { let s = bundle[k]; if(s == null) return k;
                     if(p) for(const key in p) s = s.split("{"+key+"}").join(String(p[key])); return s; } };
                window.__render = d => mod.render(document.getElementById('w'), d, window.__ctx);
            }""", [f"http://127.0.0.1:{port}/widgets/agenda/widget.js", _ES])
            pg._errors = errors
            yield pg
            browser.close()
    finally:
        srv.terminate()


def _render(pg, data) -> None:
    pg.evaluate("d => window.__render(d)", data)


def test_open_shows_that_appointments_card_on_the_day_asked(page, views):
    plain, opened, _ = views
    _render(page, plain)
    assert page.locator(".agpanel").count() == 0
    _render(page, opened)
    panel = page.locator(".agpanel")
    assert panel.count() == 1, "the card did not open"
    text = panel.inner_text()
    assert "Piano de Abril" in text
    assert str(WK3.day) in text, f"the card is not on {WK3}: {text}"


def test_a_refresh_with_the_same_push_does_not_reopen_a_card_he_closed_by_hand(page, views):
    _, opened, _ = views
    _render(page, opened)
    page.locator(".agpanel .agpx").click()
    _render(page, opened)                                          # same token: a plain refresh
    assert page.locator(".agpanel").count() == 0


def test_close_takes_the_card_away_and_leaves_the_view(page, views):
    plain, opened, closed = views
    _render(page, plain)
    _render(page, {**opened, "view": {**opened["view"], "n": opened["view"]["n"] + 100}})
    assert page.locator(".agpanel").count() == 1
    tab_before = page.locator(".agtab.on").inner_text()
    _render(page, {**closed, "view": {**closed["view"], "n": opened["view"]["n"] + 101}})
    assert page.locator(".agpanel").count() == 0, "«cierra la ficha» left the card open"
    assert page.locator(".agtab.on").inner_text() == tab_before


def test_no_script_error(page):
    assert not page._errors, page._errors
