"""V2-769 — rendered: a weekly appointment is on the card in week three, says it repeats, and can be cancelled
for one day or for the whole series.

His report, 2026-09-25, read off this very card: *«en la semana del veintiuno al veintisiete… solo veo un ítem
el martes. Cambio a la semana del veintiocho al cuatro de octubre, solo veo un ítem el jueves… y del cinco al
once de octubre no veo ningún ítem»*. So the measurement is the one he made: step the WEEK view forward and
look. The data is the product's own `view_data()` after a real `add_meeting` with the call the model sent; the
card is the real `widget.js`.
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
UNTIL = TUE + dt.timedelta(weeks=30)
#: How many «›» presses from this week to the week holding the first Tuesday (weeks start on Monday).
FIRST_WEEK = ((TUE - dt.timedelta(days=TUE.weekday())) - (TODAY - dt.timedelta(days=TODAY.weekday()))).days // 7


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
def data():
    """The product's own view after the exact call the model made, in an isolated store."""
    from widgets.agenda import data as agenda, gcal
    real_svc = gcal.svc
    gcal.svc = lambda: None
    try:
        agenda.apply_action("clear_all", {})
        res = agenda.apply_action("add_meeting", {
            "title": "Piano de Abril", "date": TUE.isoformat(), "startTime": "15:15", "endTime": "16:00",
            "recurrence": "weekly", "repeatUntil": UNTIL.isoformat(), "category": "familia"})
        assert res.get("ok") is not False, res
        yield agenda.view_data()
        agenda.apply_action("clear_all", {})
    finally:
        gcal.svc = real_svc


@pytest.fixture(scope="module")
def page(data):
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
            pg._mount_args = [f"http://127.0.0.1:{port}/widgets/agenda/widget.js", data, _ES]
            pg._errors = errors
            yield pg
            browser.close()
    finally:
        srv.terminate()


def _mount(pg) -> None:
    """A fresh card for every look — an open panel from the previous test must not cover this one."""
    pg.set_content("<div id='w' style='width:900px;height:700px'></div>")
    pg.evaluate("""async ([src, data, bundle]) => {
                window.__calls = [];
                const mod = await import(src);
                const ctx = { action: (n, p) => { window.__calls.push([n, p]); return Promise.resolve(data); },
                              top: () => {}, running: true, lang: "es",
                              t: (k, p) => { let s = bundle[k]; if(s == null) return k;
                                 if(p) for(const key in p) s = s.split("{"+key+"}").join(String(p[key]));
                                 return s; } };
                mod.render(document.getElementById('w'), data, ctx);
            }""", pg._mount_args)


def _week(pg, weeks_ahead: int) -> list[str]:
    _mount(pg)
    pg.click(".agtab[data-view=week]")
    pg.click(".agnav [data-nav=today]")
    for _ in range(weeks_ahead):
        pg.click(".agnav [data-nav=next]")
    return pg.locator(".agev").all_inner_texts()


def test_the_series_is_there_every_week_he_looked_at(page):
    first = FIRST_WEEK
    for k in (0, 1, 2, 5):
        texts = _week(page, first + k)
        assert any("Piano de Abril" in t for t in texts), f"week +{first + k} has no piano: {texts}"


def test_the_panel_says_it_repeats_and_until_when(page):
    _week(page, FIRST_WEEK + 2)
    page.locator(".agev", has_text="Piano de Abril").first.click()
    panel = page.locator(".agpanel").inner_text()
    assert "↻ Se repite cada semana: martes" in panel, panel
    assert str(UNTIL.year) in panel, panel


def test_cancelling_offers_one_day_or_the_whole_series(page):
    _week(page, FIRST_WEEK + 2)
    page.locator(".agev", has_text="Piano de Abril").first.click()
    page.locator(".agpanel button.risk").first.click()           # «Cancelar cita» → confirm step
    labels = page.locator(".agpanel button.risk").all_inner_texts()
    assert "Solo este día" in labels and "Toda la serie" in labels, labels
    page.locator(".agpanel button.risk", has_text="Toda la serie").click()
    calls = page.evaluate("window.__calls")
    assert calls and calls[-1][0] == "cancel_meeting" and calls[-1][1].get("whole") is True, calls


def test_no_script_error(page):
    assert not page._errors, page._errors
