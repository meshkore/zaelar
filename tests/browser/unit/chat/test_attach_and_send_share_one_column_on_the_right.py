"""V2-831 T-03 — the composer gives the text box the whole width: attach and send stand in ONE column on its
right, touching, same size. Rendered: the real ChatWall + store + stylesheet in Chromium, the engine mocked.

Measured at a desktop width and at a phone width (375 px), with and without a file in the tray:
  · the textarea's left edge is the composer's own left edge (no control eats width on the left);
  · attach and send share the same x-column, to the right of the textarea;
  · attach sits on top of send, vertically adjacent (a gap no wider than the design system's smallest step),
    both the same size.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
_EN = json.loads((ENGINE / "i18n/genesis/en/ui.json").read_text(encoding="utf-8"))

pytest.importorskip("playwright.sync_api")

LIMITS = {"max_file_bytes": 1048576, "max_files_per_message": 10, "max_message_bytes": 4194304,
          "upload_stall_s": 5, "process_timeout_s": 5}
TOL = 1.0  # px — sub-pixel rounding


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def browser_and_port():
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            yield b, port
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _page(browser, port, width, height):
    pg = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/files/limits", lambda r: r.fulfill(status=200, content_type="application/json",
                                                         body=json.dumps(LIMITS)))
    pg.route("**/api/files/upload**", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(
        {"ok": True, "name": "notes.txt", "size": 8, "episode_id": 101, "kind": "text", "thumb": None, "read": True})))
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"strings": _EN})))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async () => {
        localStorage.clear();
        for (const h of ['/frontend/app/core/palette.css', '/frontend/app/styles.css']) {
          const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l);
          await new Promise(r => { l.onload = r; l.onerror = r; }); }
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle('en'); if (i18n.applyLang) await i18n.applyLang('en');
        const store = await import('/frontend/app/core/store.js?v=2');
        const wall = await import('/frontend/app/components/ChatWall.js?v=5');
        document.body.append(wall.ChatWall());
        store.openChatFrom('orb'); store.setChatTab('chat');
    }""")
    pg.wait_for_selector("#chatwall.open .cw-input textarea", timeout=5000)
    pg._errors = errors
    return pg


def _geometry(pg):
    return pg.evaluate("""() => {
        const q = s => document.querySelector('#chatwall ' + s);
        const r = el => { const b = el.getBoundingClientRect();
                          return {l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height}; };
        const box = q('.cw-input'), cs = getComputedStyle(box);
        return {box: r(box), padL: parseFloat(cs.paddingLeft), ta: r(q('.cw-input textarea')),
                clip: r(q('.cw-clip')), send: r(q('.cw-send')),
                step: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--sp-2')) || 8};
    }""")


def _assert_one_column_on_the_right(g, where):
    ta, clip, send = g["ta"], g["clip"], g["send"]
    assert abs(ta["l"] - (g["box"]["l"] + g["padL"])) <= TOL, \
        f"{where}: the textarea must start at the composer's left edge, nothing on its left: {g}"
    assert abs(clip["l"] - send["l"]) <= TOL and abs(clip["r"] - send["r"]) <= TOL, \
        f"{where}: attach and send must share one x-column: clip={clip} send={send}"
    assert clip["l"] >= ta["r"] - TOL, f"{where}: the column must be to the RIGHT of the textarea: ta={ta} clip={clip}"
    assert clip["b"] <= send["t"] + TOL, f"{where}: attach sits on top of send: clip={clip} send={send}"
    assert send["t"] - clip["b"] <= g["step"] + TOL, \
        f"{where}: attach and send must touch (gap ≤ one small step): clip={clip} send={send}"
    assert abs(clip["w"] - send["w"]) <= TOL and abs(clip["h"] - send["h"]) <= TOL, \
        f"{where}: attach and send are the same size: clip={clip} send={send}"
    assert send["r"] <= g["box"]["r"] + TOL, f"{where}: the column stays inside the composer: {g}"


@pytest.mark.parametrize("width,height", [(1280, 800), (375, 812)], ids=["desktop", "phone-375"])
def test_attach_and_send_share_one_column_on_the_right(browser_and_port, width, height):
    b, port = browser_and_port
    pg = _page(b, port, width, height)
    _assert_one_column_on_the_right(_geometry(pg), f"{width}px, empty")

    # A file in the tray (full row above) leaves the column where it was.
    with pg.expect_file_chooser() as fc:
        pg.click("#chatwall .cw-clip")
    fc.value.set_files([{"name": "notes.txt", "mimeType": "text/plain", "buffer": b"buy milk"}])
    until_sync(lambda: pg.locator("#chatwall .cw-att-chip[data-phase=ready]").count() == 1, "the file to be ready")
    g = _geometry(pg)
    _assert_one_column_on_the_right(g, f"{width}px, one file in the tray")
    tray = pg.evaluate("() => { const b = document.querySelector('#chatwall .cw-att-tray').getBoundingClientRect();"
                       " return {b: b.bottom}; }")
    assert tray["b"] <= min(g["ta"]["t"], g["clip"]["t"]) + TOL, "the tray stays above the text box and the column"
    assert not pg._errors, pg._errors
    pg.close()
