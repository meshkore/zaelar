#
# The operator's live report, 2026-09-18: inside an open thread, below each
# message sits "an okay flag, then an x, then a subwoofer-looking symbol" that
# makes no sense. Root cause: the per-message action buttons were emoji TEXT
# (check / cross / filing-cabinet / trash / muted-speaker), so each machine's
# glyph font drew them differently. The fix renders the same five actions, in
# the same order, as inline SVG. This test pins that: every action button must
# carry an SVG icon and no emoji text, and clicking must still fire the same
# store action.
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

_EMOJI = ["✓", "✕", "🔇", "🗄", "🗑", "…"]

_WA = {"messageId": "w1", "chatId": "111", "platform": "whatsapp", "from": "Francisco",
       "group": "Francisco", "body": "hola", "ts": 1, "n": 1}
_MAIL = {"messageId": "m1", "chatId": "222", "platform": "email", "from": "carwow@example.com",
         "group": "carwow@example.com", "body": "offer", "ts": 2, "n": 2}


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
    """Mount the card with a chosen profile. The profile is read from localStorage at MODULE LOAD."""
    page.goto(page._hb_origin)
    page.evaluate("p => localStorage.setItem('hb-msg-profile', p)", profile)
    page.goto(page._hb_origin)          # fresh document → the module reads the profile we just stored
    page.set_content("<div id='w'></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src + '?v=' + Math.random());
             window.__ctx = { action: (name, payload) => { window.__calls.push([name, payload || {}]); },
                              top: () => {}, running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_widget_url, data],
    )


def _data(items, active=None):
    return {"platforms": {"whatsapp": {"status": "connected"}, "email": {"status": "connected"}},
            "items": items,
            "chats": [{"n": 1, "name": "Francisco", "platform": "whatsapp", "count": 1, "chatId": "111"}],
            "active_chat": active,
            "active_items": items if active else []}


def _assert_no_emoji_buttons(page, scope: str):
    buttons = page.locator(f"{scope} button")
    assert buttons.count() > 0, f"{scope}: no action buttons painted at all"
    for i in range(buttons.count()):
        text = buttons.nth(i).inner_text()
        for glyph in _EMOJI:
            assert glyph not in text, f"{scope} button {i} still carries emoji text {glyph!r}"
        assert buttons.nth(i).locator("svg").count() == 1, \
            f"{scope} button {i} has no inline SVG icon"


def test_the_thread_action_row_is_svg_icons_not_emoji(_page):
    _mount(_page, _data([_WA, _MAIL], {"platform": "whatsapp", "chatId": "111"}), "simple")
    _assert_no_emoji_buttons(_page, ".tacts")


def test_the_email_thread_offers_archive_and_trash_as_icons(_page):
    _mount(_page, _data([_MAIL], {"platform": "email", "chatId": "222"}), "simple")
    buttons = _page.locator(".tacts button")
    assert buttons.count() == 5, \
        f"email thread must offer check/close/archive/trash/mute, found {buttons.count()}"
    _assert_no_emoji_buttons(_page, ".tacts")


def test_the_rich_list_action_row_is_svg_icons_not_emoji(_page):
    highlighted = dict(_WA, highlight=True)
    _mount(_page, _data([highlighted]), "completo")
    _assert_no_emoji_buttons(_page, ".acts")


def test_clicking_the_icon_buttons_still_fires_the_same_actions(_page):
    _mount(_page, _data([_WA], {"platform": "whatsapp", "chatId": "111"}), "simple")
    _page.locator(".tacts button").nth(0).click()
    _page.locator(".tacts button").nth(2).click()
    calls = _page.evaluate("window.__calls")
    assert ["read", {"n": 1}] in calls, f"check icon must fire read, got {calls}"
    assert ["hide", {"n": 1}] in calls, f"mute icon must fire hide, got {calls}"
    mute = _page.locator(".tacts button").nth(2)
    assert mute.is_disabled(), "mute must stay busy-blocked after the press"
    assert mute.locator("svg").count() == 1, "busy feedback must keep the icon, not wipe it"
