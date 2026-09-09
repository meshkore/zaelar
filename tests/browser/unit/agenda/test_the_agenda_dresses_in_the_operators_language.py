# V2-639 — the agenda's own chrome follows the active language (the V2-613 `ctx.t`/`ctx.lang` seam), and an
# appointment's details are one hover away. Rendered, not read: whether a tab says "Week", whether the month
# header comes out in the viewer's locale shape, and whether a meeting cell carries its notes as a tooltip
# are all invisible to a source grep.
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
    page.set_content("<div id='w' style='width:660px'></div>")
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


def test_the_tabs_speak_english_through_the_real_bundle(_page):
    _mount(_page, _data(days=_days()), lang="en", bundle=_EN)
    labels = _page.locator(".agtab").all_inner_texts()
    assert "Week" in labels and "Month" in labels
    assert labels[0] == "Today" and labels[1] == "Tomorrow"
    assert "Semana" not in labels


def test_without_the_seam_the_spanish_fallbacks_stand(_page):
    _mount(_page, _data(days=_days()))
    labels = _page.locator(".agtab").all_inner_texts()
    assert "Semana" in labels and "Mes" in labels
    assert labels[0] == "Hoy" and labels[1] == "Mañana"


def test_the_month_header_comes_out_in_the_viewers_locale(_page):
    _mount(_page, _data(days=_days()), lang="en", bundle=_EN)
    _page.click(".agtab[data-sel=month]")
    header = _page.locator(".agmnav b").inner_text()
    month_en = time.strftime("%B")
    assert month_en.lower() in header.lower(), header


def test_a_meetings_notes_are_one_hover_away_in_the_month_grid(_page):
    meets = [{"title": "Dentista", "date": _today(), "startTime": "17:00", "endTime": "18:00",
              "notes": "Clínica Ruiz, llevar la radiografía"}]
    _mount(_page, _data(days=_days(), meetings=meets))
    _page.click(".agtab[data-sel=month]")
    ev = _page.locator(".agev").first
    assert "Dentista" in ev.inner_text()
    assert ev.get_attribute("title") == "Clínica Ruiz, llevar la radiografía"


def test_the_week_view_empty_row_and_action_buttons_follow_the_bundle(_page):
    _mount(_page, _data(days=_days()), lang="en", bundle=_EN)
    _page.click(".agtab[data-sel=week]")
    assert "no meetings" in _page.locator(".agweek").inner_text()
    _mount(_page, _data(days=_days()), lang="en", bundle=_EN)
    assert _page.locator(".replan").inner_text().endswith("Replan")


def test_a_pushed_month_view_still_lands(_page):
    """The live bug's other half: once show_day resolves the alias, the push must move the widget."""
    _mount(_page, _data(days=_days(), view={"sel": "month", "n": 1, "at": time.time()}))
    assert _page.locator(".agmonth").count() == 1, "the pushed view selected the month tab on mount"
