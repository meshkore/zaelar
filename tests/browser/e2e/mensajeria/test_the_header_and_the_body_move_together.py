"""V2-626 — the header and the body are ONE state, RENDERED: naming a channel (by voice or by tap) leaves
whatever screen was underneath, and the specific request wins when a payload carries both.

The operator's screenshot (2026-09-09): he asked for his mail, the email dot lit up — and the WhatsApp
connector screen stayed sitting below it. `_platFilter` had moved and `_screen` had not, so `showChannels`
returned early and the whole lens never rendered. Selecting a channel is state MECHANICS, not routing logic:
whoever asks, the body follows. Only a render can see this — the source assigns the filter either way.
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "mensajeria", "widget.js")

_HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body><div id="host"></div></body></html>"""

_NOW = time.time()
_ITEMS = [
    {"n": 1, "platform": "email", "from": "Ana", "subject": "Presupuesto", "body": "te paso el número",
     "ts": _NOW - 600, "urgencia": "media", "dirigido_a_mi": True, "highlight": True, "chatId": "ana@x.com"},
    {"n": 2, "platform": "whatsapp", "from": "Luis", "body": "¿comemos?", "ts": _NOW - 900,
     "urgencia": "media", "dirigido_a_mi": True, "highlight": True, "chatId": "34600"},
]
_BASE = {
    "platforms": {"whatsapp": {"status": "connected"}, "telegram": {"status": "connected"},
                  "email": {"status": "connected"}},
    "updated": "10:00:00", "items": _ITEMS, "count": 2,
    "chats": [{"platform": "whatsapp", "chatId": "34600", "name": "Luis", "n": 2, "count": 1,
               "highlight": True, "dirigido_a_mi": True, "last": "¿comemos?", "ts": _NOW - 900}],
    "active_chat": None, "active_items": [], "muted_channels": [], "notify_policy": {},
    "connect_focus": None, "view": None, "lens_criteria": {}, "activity_chats": [], "autoresponder": {},
}
# The screenshot's starting point: the brain was asked to connect WhatsApp, so that wizard is on screen.
_ON_WIZARD = {**_BASE, "connect_focus": {"platform": "whatsapp", "ts": 1000}}
# «Enséñame el correo» — the SAME payload the server pushes for show_view {platform:'email'}.
_SAY_EMAIL = {**_BASE, "connect_focus": {"platform": "whatsapp", "ts": 1000},
              "view": {"platform": "email", "n": 1, "at": _NOW}}
# One payload asking for BOTH: a coarse lens change and a specific connector to open. The specific one wins.
# ts must be the highest seen in this page: `connect_focus` is honoured once, by a MOVING stamp.
_BOTH = {**_BASE, "connect_focus": {"platform": "telegram", "ts": 4000},
         "view": {"platform": "email", "n": 2, "at": _NOW}}
# «Vuelve al WhatsApp» while an email is open on screen (a detail screen is a screen too).
_SAY_WA = {**_BASE, "view": {"platform": "whatsapp", "n": 3, "at": _NOW}}

_MEASURE = """() => {
  const el = document.querySelector('.hb-msg');
  return {
    // The setup area has two screens: the connector LIST (.chanhead) and one connector's wizard
    // (.crumb). Either of them being on screen means the messages are not.
    onSetupScreen: !!el.querySelector('.crumb, .chanhead'),
    onMailDetail: !!el.querySelector('.mdet'),
    pendingConfirm: !!el.querySelector('.cfm'),
    mails: [...el.querySelectorAll('.mrow .mfrom')].map(n => n.textContent),
    chats: [...el.querySelectorAll('.chatrow .tfrom')].map(n => n.textContent),
    lit: [...el.querySelectorAll('.dots .filt')].map(n => (n.title||'').split(':')[0]),
  };
}"""


async def _mount(pg, data):
    await pg.evaluate(
        "d => { window.__acts = []; window.render(document.getElementById('host'), d, "
        "{action: async (name, payload) => { window.__acts.push([name, payload]); return {}; },"
        " top: () => {}}) }", data)
    await pg.wait_for_timeout(60)


async def _click(pg, sel):
    """Click if it is there. A missing element is a MEASUREMENT here, not a harness crash: when this
    regresses, the screen that should have yielded is still on top and the row simply is not on the page —
    that has to reach the assertions as a red assertion, not as a 30 s timeout that errors every case."""
    try:
        await pg.click(sel, timeout=1500)
    except Exception:
        return False
    await pg.wait_for_timeout(60)
    return True


def _run():
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 560, "height": 900})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))

            async def _page(route):
                await route.fulfill(status=200, content_type="text/html", body=_HTML)
            await pg.route("http://zaelar.test/", _page)
            await pg.goto("http://zaelar.test/")
            src = open(_WIDGET, encoding="utf-8").read()
            await pg.add_script_tag(content=src.replace("export function render", "window.render = function render"))

            out = {}
            await _mount(pg, _ON_WIZARD)
            out["wizard"] = await pg.evaluate(_MEASURE)      # the starting screen, as in the screenshot
            await _mount(pg, _SAY_EMAIL)                     # …and now he asks for his mail
            out["voice_email"] = await pg.evaluate(_MEASURE)

            # The same order given by TAP, from the setup screen: one door, one behaviour.
            await _mount(pg, _ON_WIZARD)
            await _mount(pg, {**_ON_WIZARD, "connect_focus": {"platform": "whatsapp", "ts": 3000}})
            await _click(pg, ".dots .picon[title^='WhatsApp']")
            out["tap"] = await pg.evaluate(_MEASURE)

            # Both in one payload: the specific request (open Telegram's wizard) is the one left standing.
            await _mount(pg, _BOTH)
            out["both"] = await pg.evaluate(_MEASURE)

            # A mail detail is a screen too: open one, then name another channel by voice.
            await _mount(pg, {**_BASE, "view": {"platform": "email", "n": 5, "at": _NOW}})
            await _click(pg, ".mrow")
            out["mail_open"] = await pg.evaluate(_MEASURE)
            await _mount(pg, {**_SAY_WA, "view": {"platform": "whatsapp", "n": 6, "at": _NOW}})
            out["voice_wa"] = await pg.evaluate(_MEASURE)

            # SAME channel, from its own detail screen: «enséñame el correo» with a mail open asks for
            # that channel's LIST. The platform guard cannot catch this one — the lens does not change.
            await _mount(pg, {**_BASE, "view": {"platform": "email", "n": 7, "at": _NOW}})
            await _click(pg, ".mrow")
            out["mail_open2"] = await pg.evaluate(_MEASURE)
            await _mount(pg, {**_BASE, "view": {"platform": "email", "n": 8, "at": _NOW}})
            out["same_lens"] = await pg.evaluate(_MEASURE)

            # A pending destructive confirmation must not be waiting when he comes back to the setup screen.
            await _mount(pg, {**_BASE, "connect_focus": {"platform": "whatsapp", "ts": 9000}})
            await _click(pg, ".linkcard .bt-ghost")           # «Desconectar» → asks for confirmation
            out["confirm_up"] = await pg.evaluate(_MEASURE)
            await _mount(pg, {**_BASE, "view": {"platform": "email", "n": 9, "at": _NOW}})
            await _click(pg, ".connbtn")                      # back into Conectores by hand
            out["back_in"] = await pg.evaluate(_MEASURE)
            # …and back into THAT connector's own screen, the only place the confirmation would show.
            await _click(pg, ".igrid .ibox:has(.ilabel:text-is('WhatsApp'))")
            out["back_in_wizard"] = await pg.evaluate(_MEASURE)

            out["errors"] = errors
            await b.close()
            return out
    return asyncio.run(go())


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


@pytest.fixture(scope="module")
def result(playwright_available):
    return _run()


def test_the_setup_screen_is_where_this_starts(result):
    assert result["errors"] == [], result["errors"]
    assert result["wizard"]["onSetupScreen"] is True


def test_a_voiced_channel_leaves_the_setup_screen_and_paints_its_own(result):
    """The bug in the screenshot: the dot lit, the body did not move."""
    m = result["voice_email"]
    assert m["onSetupScreen"] is False, "the connectors screen survived a pushed view"
    assert m["mails"] == ["Ana"], m


def test_a_tapped_channel_does_the_same_thing(result):
    assert result["tap"]["onSetupScreen"] is False


def test_the_specific_request_wins_when_one_payload_carries_both(result):
    assert result["both"]["onSetupScreen"] is True, "a lens change wiped the wizard that was asked for"


def test_an_open_mail_is_a_screen_and_yields_too(result):
    assert result["mail_open"]["onMailDetail"] is True
    m = result["voice_wa"]
    assert m["onMailDetail"] is False, "the mail detail survived a change of channel"
    assert m["chats"] == ["Luis"], m


def test_the_same_channel_from_its_detail_lands_on_that_channels_list(result):
    """The platform guard cannot see this one: the lens does not change, only the screen has to."""
    assert result["mail_open2"]["onMailDetail"] is True
    m = result["same_lens"]
    assert m["onMailDetail"] is False, "asking for the mail while reading one kept the detail"
    assert m["mails"] == ["Ana"], m


def test_a_pending_disconnect_confirmation_does_not_wait_for_him(result):
    assert result["confirm_up"]["pendingConfirm"] is True
    assert result["back_in"]["onSetupScreen"] is True
    assert result["back_in_wizard"]["onSetupScreen"] is True
    assert result["back_in_wizard"]["pendingConfirm"] is False, "a destructive confirmation survived leaving"
