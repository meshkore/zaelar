# V2-639/V2-643 — the agenda's own chrome follows the active language (the V2-613 `ctx.t`/`ctx.lang` seam),
# and its details are one hover away. Rendered, not read: whether a view tab says "Week", whether the range
# title comes out in the viewer's locale shape, and whether a month cell carries its notes are all invisible
# to a source grep.
from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
_EN = json.loads((_ENGINE / "i18n/bundles/en.json").read_text())


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _data(**over):
    d = {"date": _today(), "now": "12:00", "mission": "", "plan": {"blocks": [], "focus": []},
         "active": None, "days": [], "todayIndex": 0, "meetings": [], "projects": [],
         "view": None, "calendars": [], "warnings": [], "coaching": []}
    d.update(over)
    return d


def _days():
    base = time.time()
    out = []
    for i in range(7):
        d = time.localtime(base + i * 86400)
        out.append({"date": time.strftime("%Y-%m-%d", d), "label": "X", "weekday": "X",
                    "plan": {"blocks": [], "focus": [], "summary": ""}})
    return out


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
            page = browser.new_page()
            page._hb_url = f"http://127.0.0.1:{port}/widgets/agenda/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/agenda/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data, *, lang=None, bundle=None):
    """lang+bundle -> a ctx with the V2-613 seam; without them the bare-fallback path renders."""
    page.goto(page._hb_origin)
    page.set_content("<div id='w' style='width:820px'></div>")
    page.evaluate(
        """async ([src, data, lang, bundle]) => {
             const mod = await import(src);
             const ctx = { action: () => Promise.resolve({ok:true}), top: () => {}, running: true };
             if(lang){ ctx.lang = lang; ctx.t = (k, p) => {
               let s = bundle[k]; if(s == null) return k;
               if(p) for(const key in p) s = s.split("{"+key+"}").join(String(p[key]));
               return s; }; }
             mod.render(document.getElementById('w'), data, ctx);
           }""",
        [page._hb_url, data, lang, bundle or {}])


def test_the_views_speak_english_through_the_real_bundle(_page):
    _mount(_page, _data(days=_days()), lang="en", bundle=_EN)
    labels = _page.locator(".agtab").all_inner_texts()
    assert labels == ["Day", "Week", "Month", "List"], labels
    assert _page.locator(".agnav [data-nav=today]").inner_text() == "Today"


def test_without_the_seam_the_spanish_fallbacks_stand(_page):
    _mount(_page, _data(days=_days()))
    labels = _page.locator(".agtab").all_inner_texts()
    assert labels == ["Día", "Semana", "Mes", "Lista"], labels
    assert _page.locator(".agnav [data-nav=today]").inner_text() == "Hoy"


def test_the_range_title_comes_out_in_the_viewers_locale(_page):
    _mount(_page, _data(days=_days()), lang="en", bundle=_EN)
    _page.click(".agtab[data-view=month]")
    header = _page.locator(".agrange").inner_text()
    assert time.strftime("%B").lower() in header.lower(), header


def test_a_meetings_notes_and_details_are_in_its_panel(_page):
    meets = [{"title": "Dentista", "date": _today(), "startTime": "17:00", "endTime": "18:00",
              "notes": "Clínica Ruiz, llevar la radiografía", "location": "Calle Mayor 3",
              "attendees": ["Ana", "Luis"], "status": "pending", "remindAt": "2026-09-09 15:00"}]
    _mount(_page, _data(days=_days(), meetings=meets))
    _page.click(".agtab[data-view=day]")
    _page.click(".agev")
    panel = _page.locator(".agpanel").inner_text()
    assert "Dentista" in panel and "radiografía" in panel
    assert "Calle Mayor 3" in panel and "Ana" in panel
    assert "confirmar" in panel.lower(), "a pending invitation SAYS the other side has not answered"


def test_the_coach_rail_survives_in_the_day_view(_page):
    """The agenda has always been a coach too (Now + countdown + done/snooze/not_now/drop). The redesign
    moves it beside the day grid; losing it would be a feature deleted by a restyle."""
    active = {"start": "12:00", "end": "13:00", "label": "Revisar contrato", "kind": "deep",
              "taskId": "t1", "remaining_min": 25}
    _mount(_page, _data(days=_days(), active=active,
                        plan={"blocks": [{"start": "12:00", "end": "13:00", "label": "Revisar contrato",
                                          "kind": "deep", "taskId": "t1"}], "focus": []}))
    _page.click(".agtab[data-view=day]")
    side = _page.locator(".agside").inner_text()
    assert "Revisar contrato" in side
    assert _page.locator(".agacts [data-a=done]").count() == 1
    assert _page.locator("[data-a=replan]").count() == 1
