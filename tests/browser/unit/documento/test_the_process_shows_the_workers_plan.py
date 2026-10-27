# V2-820 — the process tab of a report errand shows the steps the worker DECLARED, with the done ones ticked and the
# current one marked, instead of «Preparando… · Aún no hay pasos que contar» while the worker was working through a
# five-step plan. Rendered, not read from source: which row is marked and what the headline says are invisible to a
# grep. The steps are the worker's words (es and en here); the card invents none.
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



PLANS = {
    "es": ["Leer tus mensajes enviados", "Analizar cómo escribes", "Crear el documento", "Presentártelo"],
    "en": ["Read your sent emails", "Analyse how you write", "Write the document", "Present it to you"],
}


@pytest.mark.parametrize("lang", sorted(PLANS))
def test_the_declared_plan_is_the_account_with_the_current_step_marked(page, lang):
    plan = PLANS[lang]
    _mount(page, _view(process={"alive": True, "phases": [], "plan": plan, "done": 1, "title": ""}))
    steps = page.locator(".hbd-pstep")
    assert steps.count() == len(plan)
    assert [t.split("\n")[-1].strip() for t in steps.all_inner_texts()] == plan
    assert "done" in (steps.nth(0).get_attribute("class") or "")
    assert "now" in (steps.nth(1).get_attribute("class") or ""), "the step being worked on is marked"
    assert page.locator(".hbd-pnow").inner_text() == plan[1], "with no line yet, the headline is the current step"
    assert page.locator(".hbd-pempty").count() == 0, "«no steps to tell» is false while a plan is on the card"


def test_the_narrative_lines_stay_under_the_plan(page):
    plan = PLANS["es"]
    _mount(page, _view(process={"alive": True, "phases": ["Recorriendo el archivo por chats"], "plan": plan,
                                "done": 0, "title": ""}))
    assert page.locator(".hbd-pstep").count() == len(plan)
    assert page.locator(".hbd-prow").all_inner_texts() == ["Recorriendo el archivo por chats"]
    assert page.locator(".hbd-pnow").inner_text() == "Recorriendo el archivo por chats"


def test_no_plan_and_no_line_still_says_so_and_a_finished_errand_shows_no_plan(page):
    _mount(page, _view(process={"alive": True, "phases": [], "title": ""}))
    assert page.locator(".hbd-pstep").count() == 0 and page.locator(".hbd-pempty").count() == 1
    _mount(page, _view(process={"alive": False, "phases": ["hecho"], "plan": PLANS["en"], "done": 4, "title": ""}))
    assert page.locator(".hbd-pstep").count() == 0
