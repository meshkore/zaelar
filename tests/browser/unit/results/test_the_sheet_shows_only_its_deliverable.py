"""The results sheet is the errand's DELIVERABLE and nothing else — it has no process tab (V2-822), RENDERED.

The operator (2026-10-27): simplify the cards and move the process to the processes panel. The «Proceso» tab — the
narration, the harvest, the browser's capture — is gone from the sheet; what the errand is doing lives under the
running process's row. What stays on the sheet: the Results tab carries the loader while the errand works (an empty
list says where the steps are), and when the page needs HIM (a wall, a login, a question) the page shows above the
tab with its button — that is a request to him, not progress.

Mounted in Chromium from the real widget.js, driving `render()` with the payload shapes the backend sends.
Disarm: put `{id: "process"}` back in `TABS` → red.
"""
from __future__ import annotations

import base64
import pathlib
import socket
import subprocess
import sys

import pytest

from tests.waiting import until_sync

pytest.importorskip("playwright.sync_api")

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")

_ALIVE = {"title": "Monitores", "items": [], "progress": {"alive": True, "phases": ["entrando en pccomponentes"]},
          "browser": {}, "harvest": {"pages": 2, "rows": 9, "kept": 3}}
_ROW = [{"title": "Dell U2724D", "price": "299 €", "url": "https://example.com/a"}]
_LOGIN = {**_ALIVE, "browser": {"task_id": "t9", "shot": "shot-t9.png", "shot_rev": 3, "url": "https://x.example",
                                "page_title": "Acceso", "awaiting_login": True}}
_WALL = {**_ALIVE, "browser": {"task_id": "t9", "shot": "shot-t9.png", "shot_rev": 3, "wall": "captcha",
                               "question": "¿Reservo la de las 21:00?"}}
_BROWSING = {**_ALIVE, "browser": {"task_id": "t9", "shot": "shot-t9.png", "shot_rev": 3, "url": "https://x.example"}}


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": 900, "height": 700})
            pg.route("**/widgets/navegador/asset/**", lambda r: r.fulfill(status=200, content_type="image/png", body=_PNG))
            pg.goto(f"http://127.0.0.1:{port}/widgets/results/")
            pg.set_content("<div id='host' style='height:600px'></div>")
            pg.evaluate("""async (src) => {
                const mod = await import(src);
                window.__actions = [];
                const ctx = { action(a, p){ window.__actions.push([a, p || {}]); return Promise.resolve({ok: true}); },
                              top(){} };
                window.__render = (d) => mod.render(document.getElementById('host'), JSON.parse(JSON.stringify(d)), ctx);
            }""", f"http://127.0.0.1:{port}/widgets/results/widget.js")
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _paint(pg, data):
    pg.evaluate("(d) => window.__render(d)", data)
    return pg.evaluate("""() => {
        const tabs = [...document.querySelectorAll('.hr-tab')].map(b => b.dataset.tab);
        const on = (document.querySelector('.hr-tab.on') || {dataset: {}}).dataset.tab;
        const res = document.querySelector('.hr-tab[data-tab=results]');
        const spin = res && res.querySelector('.hr-spin');
        const anim = spin && spin.getAnimations ? spin.getAnimations().some(a => a.playState === 'running') : false;
        const panel = document.querySelector('.hr-panel');
        return {tabs, on, spinning: !!spin && anim, text: panel ? panel.innerText : '',
                shot: !!document.querySelector('.hr-panel .hr-navimg'),
                login: !!document.querySelector('.hr-panel .hr-login-btn'),
                wall: (document.querySelector('.hr-panel .hr-wall') || {}).textContent || '',
                q: (document.querySelector('.hr-panel .hr-navq') || {}).textContent || '',
                stats: !!document.querySelector('.hr-panel .hr-stat'),
                steps: document.querySelectorAll('.hr-panel .hr-step').length}; }""")


def test_the_sheet_has_no_process_tab_and_opens_on_its_results(page):
    v = _paint(page, _ALIVE)
    assert v["tabs"] == ["results", "summary", "sources", "criteria"], v["tabs"]
    assert v["on"] == "results", "the deliverable is what the sheet shows, even before its first row"
    assert v["spinning"], "while the errand works, the Results tab carries the loader — and it MOVES"
    assert "Procesos" in v["text"] and "pccomponentes" not in v["text"], \
        "an empty list says where the steps are, and tells none of them"
    assert not (v["stats"] or v["steps"]), "no harvest and no narration on the sheet"
    assert _paint(page, {**_ALIVE, "tab": "process"})["on"] == "results", "a stale persisted tab paints the list"


def test_the_loader_stays_on_results_until_the_errand_ends(page):
    assert _paint(page, {**_ALIVE, "items": _ROW})["spinning"]
    done = _paint(page, {**_ALIVE, "items": _ROW, "progress": {"alive": False, "phases": ["x"]}})
    assert not done["spinning"] and "Dell" in done["text"]


def test_the_browser_shows_on_the_sheet_only_when_the_page_needs_him(page):
    assert not _paint(page, _BROWSING)["shot"], "a page it is just reading is progress: it lives in the panel"
    v = _paint(page, _LOGIN)
    assert v["shot"] and v["login"], "a login wait shows the page and the button where he is looking"
    page.click(".hr-panel .hr-login-btn")
    acts = page.evaluate("() => window.__actions")
    assert ["auth_done", {"task_id": "t9"}] in acts, acts
    w = _paint(page, _WALL)
    assert "captcha" in w["wall"] and "21:00" in w["q"] and not w["login"], w
