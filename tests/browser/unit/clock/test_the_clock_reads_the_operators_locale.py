#
# V2-613 — clock is the pilot widget for `ctx.lang`: a hand-built template of translated WORDS cannot also
# reorder "January 5, 2026" into "5 de enero de 2026" (English and Spanish put the day and month in different
# places), so this widget hands the raw active code to `Intl.DateTimeFormat` instead of using `ctx.t` at all.
# RENDERED, same harness as musica's V2-366 test — `Intl` behavior is exactly what a source read cannot confirm.
#
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


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def mounted():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(f"http://127.0.0.1:{port}/widgets/clock/")
        page.set_content("<div id='w'></div>")
        page.evaluate("async (src) => { window.__mod = await import(src); }",
                      f"http://127.0.0.1:{port}/widgets/clock/widget.js")

        def mount(lang):
            page.evaluate(
                "(lang) => window.__mod.render(document.getElementById('w'), {}, "
                "{action: () => Promise.resolve({ok:true}), close: () => {}, lang})",
                lang,
            )
            page.wait_for_timeout(20)  # the first tick() runs synchronously, but give the DOM a beat to settle

        yield page, mount
        browser.close()
    srv.terminate()


def _dow(page):
    return page.eval_on_selector(".dow", "e => e.textContent")


def _date(page):
    return page.eval_on_selector(".date", "e => e.textContent")


def test_english_month_and_day_order(mounted):
    page, mount = mounted
    mount("en")
    assert any(d in _dow(page) for d in
               ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
    # English date order: MONTH DAY, YEAR — never "day de month de year".
    assert " de " not in _date(page)


def test_spanish_month_and_day_order(mounted):
    page, mount = mounted
    mount("es")
    assert any(d in _dow(page) for d in
               ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"])
    assert " de " in _date(page)   # Spanish date order: "D de MMMM de AAAA"


def test_a_language_switch_reformats_an_already_open_card(mounted):
    """This is the exact re-render the host's relanguage() performs: SAME widget instance, new ctx.lang."""
    page, mount = mounted
    mount("en")
    en_date = _date(page)
    mount("es")
    es_date = _date(page)
    assert en_date != es_date
    assert " de " in es_date and " de " not in en_date


def test_an_unconfigured_lang_falls_back_to_english_rather_than_crashing(mounted):
    page, _ = mounted
    page.evaluate(
        "() => window.__mod.render(document.getElementById('w'), {}, "
        "{action: () => Promise.resolve({ok:true}), close: () => {}})"   # no `lang` at all
    )
    assert _dow(page)   # rendered something, not blank/thrown
