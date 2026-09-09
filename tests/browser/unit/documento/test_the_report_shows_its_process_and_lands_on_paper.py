# V2-644 — the commissioned report, RENDERED: two tabs (Proceso with the live narrative, Documento as a white
# paper page), and the plain V2-549 document untouched when no errand ever bound the sheet.
#
# Rendered and not read from source, for the same reason as the sibling suite: whether the band appears,
# which tab is active, and what colour the paper actually paints are invisible to a grep — and the operator's
# order was literally about how this looks («como un documento de Word o un PDF, con su fondo blanco»).
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


@pytest.fixture(scope="module")
def page():
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
            pg = browser.new_page()
            pg._hb_origin = f"http://127.0.0.1:{port}/widgets/documento/"
            pg._hb_widget = f"http://127.0.0.1:{port}/widgets/documento/widget.js"
            yield pg
            browser.close()
    finally:
        srv.terminate()


def _mount(pg, view: dict, *, lang=None, bundle=None):
    pg.goto(pg._hb_origin)
    # A hostile HOST THEME on purpose: the live canvas defines these tokens (dark mode), and the paper's
    # whole claim is that it stays white ANYWAY. Without them, var(--hb-bg,#fff) resolves white in the bare
    # harness and a regression to theme-following is invisible (a disarm proved it).
    pg.set_content("<div id='w' style='width:700px;height:500px;"
                   "--hb-bg:#0d1622;--hb-ink:#e6ebf3;--hb-bg-soft:#131c2b'></div>")
    pg.evaluate(
        """async ([src, data, lang, bundle]) => {
             const mod = await import(src + '?v=' + Math.random());
             const ctx = { action: () => {}, running: true };
             if(lang){ ctx.lang = lang; ctx.t = (k) => (bundle[k] == null ? k : bundle[k]); }
             mod.render(document.getElementById('w'), data, ctx);
           }""",
        [pg._hb_widget, view, lang, bundle or {}],
    )


def _view(**kw) -> dict:
    base = {"kind": "markdown", "title": "", "subtitle": "", "body": "", "src": "", "source": "",
            "updated": 0, "chars": 0, "empty": True, "process": {"alive": False, "phases": [], "title": ""}}
    base.update(kw)
    base["empty"] = not (base["body"] or base["src"])
    base["chars"] = len(base["body"])
    return base


_PHASES = ["Buscando la empresa en einforma", "NIF B16713539 confirmado", "Revisando el BORME"]


def test_a_working_report_opens_on_its_process_with_the_live_narrative(page):
    _mount(page, _view(process={"alive": True, "phases": _PHASES, "title": "Informe: Juncadella"}))
    tabs = page.locator(".hbd-tab")
    assert tabs.all_inner_texts() == ["Proceso", "Documento"]
    assert "on" in (page.locator(".hbd-tab[data-tab=proc]").get_attribute("class") or "")
    rows = page.locator(".hbd-prow").all_inner_texts()
    assert rows == _PHASES, "the narrative IS the tab: which sources, what just happened"
    assert page.locator(".hbd-pspin").count() == 1, "a live errand shows it is working"
    assert page.locator(".hbd-pnow").inner_text() == "Revisando el BORME", \
        "the newest step is the headline while nothing is being written yet"


def test_once_the_body_grows_the_document_leads_and_the_process_says_writing(page):
    _mount(page, _view(body="# Informe\n\nPrimera sección.",
                       process={"alive": True, "phases": _PHASES, "title": ""}))
    assert "on" in (page.locator(".hbd-tab[data-tab=doc]").get_attribute("class") or ""), \
        "with a document growing, the operator reads the document — the process is one tap away"
    page.click(".hbd-tab[data-tab=proc]")
    assert page.locator(".hbd-pnow").inner_text() == "Redactando el documento…"


def test_the_delivered_document_is_a_white_page_whatever_the_theme(page):
    _mount(page, _view(title="Informe", body="# Informe\n\nTexto final.",
                       process={"alive": False, "phases": _PHASES, "title": ""}))
    sheet = page.locator(".hbd-sheet")
    assert sheet.count() == 1
    bg = sheet.evaluate("el => getComputedStyle(el).backgroundColor")
    ink = sheet.evaluate("el => getComputedStyle(el).color")
    assert bg == "rgb(255, 255, 255)", f"the paper must BE paper, got {bg}"
    assert ink != "rgb(255, 255, 255)", "white-on-white is not a document"
    # The finished process stays reachable — the account of how the report was reached is half of it.
    page.click(".hbd-tab[data-tab=proc]")
    assert page.locator(".hbd-pspin").count() == 0, "a finished errand must not pretend to be working"
    assert page.locator(".hbd-prow").count() == len(_PHASES)


def test_a_finished_errand_with_no_document_opens_on_its_process(page):
    """The errand died before writing anything: the honest default is WHAT HAPPENED, never a blank page
    with the answer's shape. This is the one case where the default expression (not the alive safety net)
    decides — a disarm proved nothing else measured it."""
    _mount(page, _view(process={"alive": False, "phases": _PHASES, "title": ""}))
    assert "on" in (page.locator(".hbd-tab[data-tab=proc]").get_attribute("class") or "")
    assert page.locator(".hbd-prow").count() == len(_PHASES)


def test_a_plain_document_without_an_errand_has_no_band_at_all(page):
    """The V2-549 recipe is untouched by the redesign: no process → no tabs, the sheet alone."""
    _mount(page, _view(title="Tortilla", body="# Tortilla\n\nCon cebolla."))
    assert page.locator(".hbd-tabs").count() == 0
    assert page.locator(".hbd-sheet").count() == 1


def test_the_tabs_speak_the_viewers_language_through_the_seam(page):
    _mount(page, _view(process={"alive": True, "phases": _PHASES, "title": ""}),
           lang="en", bundle=_EN)
    assert page.locator(".hbd-tab").all_inner_texts() == ["Process", "Document"]
