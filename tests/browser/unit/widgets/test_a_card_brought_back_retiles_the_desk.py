"""A card brought back from minimized re-tiles the desk if it now lands on another card (demo pass 53, 2026-09-29).

The monitors' results sheet was put away («ok just put that away»), the agenda opened where it had been, and when
the search finished the sheet came back at its old place — covering the agenda 100%. Executed on the REAL
`desktop.js` in chromium, with the harness of `test_a_card_with_no_room_retiles_the_desk`.
"""
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
_STUB_WIDGET = "export function mount(el){ el.textContent = 'mounted'; }\nexport default { mount };\n"
_IDS = ["uno", "dos", "tres"]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _overlaps(page) -> list:
    return page.evaluate("""() => {
        const cs = [...document.querySelectorAll('#stage .hb-win')].map(c => c.getBoundingClientRect());
        const out = [];
        for (let i = 0; i < cs.length; i++) for (let j = i + 1; j < cs.length; j++) {
            const a = cs[i], b = cs[j];
            const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
            const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
            if (w > 1 && h > 1) out.push([i, j, Math.round(w * h)]);
        }
        return out;
    }""")


def test_a_card_brought_back_over_another_retiles():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    from tests.waiting import port_listening
    port_listening(port)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 760})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            def _json(route, payload):
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

            page.route("**/widgets", lambda r: _json(r, {"widgets": [{"id": i, "name": i} for i in _IDS]}))
            page.route("**/widgets/registry", lambda r: _json(r, {"registry": []}))
            page.route("**/widgets/*/widget.js", lambda r: r.fulfill(
                status=200, content_type="application/javascript", body=_STUB_WIDGET))
            page.route("**/widgets/*/data*", lambda r: _json(r, {}))
            page.route("**/widgets/*/aliases*", lambda r: _json(r, {"ok": True, "aliases": []}))
            page.route("**/api/**", lambda r: _json(r, {}))
            page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            page.evaluate("""async (port) => {
                document.body.innerHTML = '<div id="stage"></div><div id="activity"></div>';
                const m = await import(`http://127.0.0.1:${port}/frontend/app/widgets/desktop.js?v=1`);
                window.__desk = new m.Desktop(document.getElementById('stage'));
            }""", port)
            for wid in ("uno", "dos"):
                page.evaluate("(id) => window.__desk.show(id, {data: {ok: true}})", wid)
                page.wait_for_selector(f"[data-wid='{wid}']", timeout=5000)
                page.wait_for_timeout(250)
            # put «uno» away, and move «dos» onto the place «uno» had
            page.evaluate("""() => {
                const a = document.querySelector("[data-wid='uno']"), b = document.querySelector("[data-wid='dos']");
                a.classList.add('hb-minned');
                b.style.left = a.style.left; b.style.top = a.style.top;
                b.style.width = a.style.width || (a.offsetWidth + 'px'); b.style.height = a.style.height || (a.offsetHeight + 'px');
            }""")
            page.evaluate("() => window.__desk.show('uno', {data: {ok: true}})")
            page.wait_for_timeout(500)
            assert not page.evaluate("() => document.querySelector(\"[data-wid='uno']\").classList.contains('hb-minned')")
            assert not _overlaps(page), f"the card came back over another one: {_overlaps(page)}"
            assert not errors, errors
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)
