"""A card with no free room re-tiles the desk instead of landing on another card (demo pass 30, 2026-09-28).

The placement engine answered «nothing fits» with the least-overlapping spot — which was still ON a card: the
Bitcoin document covered the monitor results at 47%, the trip sheet 43%. Now, when a fresh card finds no room,
the desk runs the same `arrange()` as the ▦ button, and every card ends in its own cell.

Executed on the REAL `desktop.js` in chromium (the canvas harness of `test_the_canvas_opens_cards_for_real`).
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


def test_three_cards_on_a_small_desk_do_not_overlap():
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
            page = browser.new_page(viewport={"width": 900, "height": 560})
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
            for wid in _IDS:
                page.evaluate("(id) => window.__desk.show(id, {data: {ok: true}})", wid)
                page.wait_for_selector(f"[data-wid='{wid}']", timeout=5000)
                page.wait_for_timeout(250)
            page.wait_for_timeout(400)
            assert page.evaluate("() => document.querySelectorAll('#stage .hb-win').length") == 3
            assert not _overlaps(page), f"cards overlap after the third one found no room: {_overlaps(page)}"
            assert not errors, errors
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)
