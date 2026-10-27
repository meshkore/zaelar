# V2-644 — the commissioned report, RENDERED: a white paper page, and the plain V2-549 document untouched when no
# errand ever bound the sheet.
# V2-822 — the card is the DELIVERABLE and nothing else: while the worker makes it, it is the document «being
# created» (a loader and one line that points to the processes panel); the Proceso tab of V2-644/V2-820 is gone,
# because the errand's steps live in ONE place — the running process's entry in the processes panel.
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
_EN = json.loads((_ENGINE / "i18n/genesis/en/ui.json").read_text())


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


def _no_process_view(pg):
    assert pg.locator(".hbd-tab, .hbd-tabs, .hbd-prow, .hbd-pstep").count() == 0, \
        "the card shows no process view of its own: the steps live in the processes panel"


def test_a_working_report_is_the_document_being_created(page):
    _mount(page, _view(process={"alive": True, "phases": _PHASES, "plan": ["a", "b"], "done": 1, "title": "Informe"}))
    _no_process_view(page)
    assert page.locator(".hbd-making .hbd-mkspin").count() == 1, "a live errand shows it is working"
    assert page.locator(".hbd-making b").inner_text() == "Creando el documento…"
    assert "Procesos" in page.locator(".hbd-making span").inner_text(), "it says where the steps are"
    assert "Revisando el BORME" not in page.locator("#w").inner_text(), "no narration on the card"


def test_once_the_body_grows_the_document_leads_under_a_live_band(page):
    _mount(page, _view(body="# Informe\n\nPrimera sección.", process={"alive": True, "phases": _PHASES, "title": ""}))
    _no_process_view(page)
    assert page.locator(".hbd-sheet").count() == 1, "with a document growing, he reads the document"
    assert page.locator(".hbd-liveband .hbd-mkspin").count() == 1, "…and the card still says it is being written"


def test_the_delivered_document_is_a_white_page_whatever_the_theme(page):
    _mount(page, _view(title="Informe", body="# Informe\n\nTexto final.",
                       process={"alive": False, "phases": _PHASES, "title": ""}))
    sheet = page.locator(".hbd-sheet")
    assert sheet.count() == 1
    bg = sheet.evaluate("el => getComputedStyle(el).backgroundColor")
    ink = sheet.evaluate("el => getComputedStyle(el).color")
    assert bg == "rgb(255, 255, 255)", f"the paper must BE paper, got {bg}"
    assert ink != "rgb(255, 255, 255)", "white-on-white is not a document"
    _no_process_view(page)
    assert page.locator(".hbd-liveband, .hbd-mkspin").count() == 0, "a finished errand must not pretend to be working"


def test_a_finished_errand_with_no_document_says_it_was_not_written(page):
    """The errand died before writing anything: the honest default is to SAY so, never a blank page with the
    answer's shape — and where how it ended can be read."""
    _mount(page, _view(process={"alive": False, "phases": _PHASES, "title": ""}))
    assert page.locator(".hbd-making.ended").count() == 1 and page.locator(".hbd-mkspin").count() == 0
    assert page.locator(".hbd-blank").count() == 0


def test_a_plain_document_without_an_errand_has_no_band_at_all(page):
    """The V2-549 recipe is untouched by the redesign: no process → no band, the sheet alone."""
    _mount(page, _view(title="Tortilla", body="# Tortilla\n\nCon cebolla."))
    assert page.locator(".hbd-liveband, .hbd-making").count() == 0
    assert page.locator(".hbd-sheet").count() == 1


def test_the_state_speaks_the_viewers_language_through_the_seam(page):
    _mount(page, _view(process={"alive": True, "phases": _PHASES, "title": ""}), lang="en", bundle=_EN)
    assert page.locator(".hbd-making b").inner_text() == _EN["widgets.documento.making_title"]
    assert page.locator(".hbd-making span").inner_text() == _EN["widgets.documento.making_hint"]
