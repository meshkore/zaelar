#
# V2-544 — an OPEN chat must paint, whichever list profile the operator picked. Verified by RENDERING: the
# defect is a `return` that happens BEFORE the branch that draws the thread, and no source-level assertion
# about `active_chat` can see it (the store was right, the data reached the card, and the screen still did
# not move — the same shape as the V2-124 dead canvas).
#
# Incident: «abre el mensaje de Francisco» sets `active_chat` through the widget's declared `open` action.
# In the «completo» profile, render() returned at the rich-list branch first, so the card kept painting the
# same flat list — everything downstream worked and the operator saw nothing happen.
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

_ACTIVE = {"platform": "whatsapp", "chatId": "111"}
_ITEMS = [
    {"messageId": "w1", "chatId": "111", "platform": "whatsapp", "from": "Francisco", "group": "Francisco",
     "body": "PINTURA RAPIDA SEGOVIA", "ts": 1, "n": 1},
]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def _page():
    # A REAL http origin: a module cannot be dynamically imported from `about:blank`/`file:`.
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
            page._hb_widget_url = f"http://127.0.0.1:{port}/widgets/mensajeria/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/mensajeria/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data: dict, profile: str):
    """Mount the card with a chosen profile. The profile is read from localStorage at MODULE LOAD, so it is
    written before the import and the page is reloaded for each one."""
    page.goto(page._hb_origin)
    page.evaluate("p => localStorage.setItem('hb-msg-profile', p)", profile)
    page.goto(page._hb_origin)          # fresh document → the module reads the profile we just stored
    page.set_content("<div id='w'></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src + '?v=' + Math.random());
             window.__ctx = { action: (name, payload) => { window.__calls.push([name, payload || {}]); },
                              running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_widget_url, data],
    )


def _data(active):
    return {"platforms": {"whatsapp": {"status": "connected"}},
            "items": _ITEMS,
            "chats": [{"n": 1, "name": "Francisco", "platform": "whatsapp", "count": 1, "chatId": "111"}],
            "active_chat": active,
            "active_items": _ITEMS if active else []}


@pytest.mark.parametrize("profile", ["simple", "completo"])
def test_an_open_chat_paints_its_thread_in_both_profiles(_page, profile):
    _mount(_page, _data(_ACTIVE), profile)
    assert _page.locator(".thread").count() == 1, \
        f"profile {profile!r}: the open chat did not paint — the card is still showing a list"
    assert "Francisco" in _page.locator(".thread").inner_text()
    assert _page.locator(".back").count() == 1, "a thread must always offer the way back to the list"


@pytest.mark.parametrize("profile", ["simple", "completo"])
def test_with_no_open_chat_each_profile_keeps_its_own_list(_page, profile):
    """The fix must not flatten the profiles: with nothing open, «completo» still draws the rich list and
    «simple» the chat list."""
    _mount(_page, _data(None), profile)
    assert _page.locator(".thread").count() == 0
    assert _page.locator("#w").inner_text().strip() != ""
