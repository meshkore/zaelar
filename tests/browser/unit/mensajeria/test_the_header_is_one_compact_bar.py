"""The messaging card's header is ONE compact bar, the same for every channel, and the chat list's tools share a row.

V2-831 T-04 (the header standard, `.meshkore/docs/conventions/zaelar-widget-header-standard.md`): the operator found
the WhatsApp screen spending four rows before the first chat (new chat · new group · the kind filters · a full-width
search), a plug drawn as an emoji that disappears on the dark ground, and a settings glyph a size smaller than every
icon beside it. RENDERED at the card's default size, on the WhatsApp lens and the mail lens, because every one of those
is a fact about layout that no source-level check can see.
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
import time

import pytest
from tests.waiting import port_listening

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]

# The canvas card at the manifest's default size (760 x 640), with the real palette so the plug is judged on the
# ground it is actually drawn on.
_HOST = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/frontend/app/core/palette.css">
<style>body{margin:0;padding:0;background:var(--canvas)}
  .hb-win{background:var(--hb-bg);display:flex;flex-direction:column;width:760px;height:640px;box-sizing:border-box}
  .hb-scroll{flex:1 1 auto;min-height:0;overflow:auto;padding:16px}</style></head><body>
  <div class="hb-win"><div class="hb-scroll"><div id="w"></div></div></div></body></html>"""

# The standard's bar: one row of 32 px targets plus its padding and hairline. A second row of controls can never fit.
_BAR_MAX = 48
_ICON = 32
_GLYPH = 18


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
    port_listening(port)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            pg = browser.new_page(viewport={"width": 800, "height": 700})
            pg._hb_base = f"http://127.0.0.1:{port}"
            yield pg
            browser.close()
    finally:
        srv.terminate()


def _data(platform):
    now = time.time()
    rows = [{"chatId": str(i), "name": f"Chat {i}", "kind": k, "unread": i % 2, "ts": now - i * 600, "preview": "hola"}
            for i, k in enumerate(("person", "group", "channel", "person"))]
    mail = [{"uid": str(90 - i), "from": f"p{i}@example.com", "fromName": f"Sender {i}", "subject": "Hello",
             "ts": now - i * 3600, "seen": bool(i)} for i in range(3)]
    return {"platforms": {p: {"status": "connected"} for p in ("whatsapp", "telegram", "email")},
            "items": [{"n": 1, "platform": "whatsapp", "chatId": "0", "from": "Chat 0", "body": "hola",
                       "highlight": True}],
            "chats": [], "active_chat": None, "active_items": [], "muted_channels": [], "drafts": {}, "sent": [],
            "view": {"platform": platform, "n": 1, "at": now},
            "chat_list": {"whatsapp": {"rows": rows, "recent_h": 72, "total": 4, "more": False, "complete": True,
                                       "loading": False, "asked": True, "error": ""}},
            "mailbox": {"folders": [{"name": "INBOX", "role": "inbox", "label": "INBOX"}], "folder": "INBOX",
                        "role": "inbox", "rows": mail, "loading": False, "asked": True, "more": False, "error": "",
                        "open": None, "draft": None}}


def _mount(page, platform):
    page.goto(page._hb_base + "/widgets/mensajeria/")
    page.set_content(_HOST)
    page.evaluate(
        """async ([src, data]) => {
             const mod = await import(src + '?v=' + Math.random());
             mod.render(document.getElementById('w'), data,
                        {action: () => {}, top: () => {}, openConnector: () => {}, running: true});
           }""",
        [page._hb_base + "/widgets/mensajeria/widget.js", _data(platform)])
    page.wait_for_selector(".hb-msg .hd")


def _boxes(page, sel):
    return page.evaluate("""s => [...document.querySelectorAll(s)].map(e => {
        const r = e.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height), Math.round(r.top)]; })""",
                         sel)


@pytest.mark.parametrize("platform", ["whatsapp", "email"])
def test_the_header_is_one_bar_no_taller_than_the_standard(page, platform):
    _mount(page, platform)
    (w, h, _), = _boxes(page, ".hb-msg .hd")
    assert h <= _BAR_MAX, f"{platform}: the header is {h}px tall — a second row of controls has crept in"


@pytest.mark.parametrize("platform", ["whatsapp", "email"])
def test_every_header_control_shares_one_icon_size(page, platform):
    _mount(page, platform)
    targets = _boxes(page, ".hb-msg .hd .homebtn, .hb-msg .hd .picon, .hb-msg .hd .hdactions > button")
    glyphs = _boxes(page, ".hb-msg .hd .homebtn svg, .hb-msg .hd .picon svg, .hb-msg .hd .hdactions > button svg")
    assert len(targets) >= 6, targets                       # house · 3 channels · plug · settings (· mark read)
    assert {(w, h) for w, h, _ in targets} == {(_ICON, _ICON)}, f"{platform}: targets of mixed sizes {targets}"
    assert len(glyphs) == len(targets), "a control is drawn without a stroke icon (an emoji or a text glyph)"
    assert {(w, h) for w, h, _ in glyphs} == {(_GLYPH, _GLYPH)}, f"{platform}: glyphs of mixed sizes {glyphs}"
    # Every control sits on the same line: one bar, not a cluster that wrapped.
    assert len({t for _, _, t in targets}) == 1, f"{platform}: the header controls wrapped onto two lines {targets}"


@pytest.mark.parametrize("platform", ["whatsapp", "email"])
def test_the_plug_and_settings_are_labelled_icons_not_emoji(page, platform):
    _mount(page, platform)
    texts = page.evaluate("""() => [...document.querySelectorAll('.hb-msg .hd .hdactions > button')]
        .map(b => [b.textContent.trim(), b.getAttribute('aria-label') || ''])""")
    assert texts and all(t == "" and label for t, label in texts), \
        f"every action is an icon carrying its word in aria-label, never a glyph in the text: {texts}"


def test_the_chat_list_tools_share_one_row_with_the_search(page):
    _mount(page, "whatsapp")
    (sw, sh, stop), = _boxes(page, ".hb-msg .cxbar .cxsearch")
    row = _boxes(page, ".hb-msg .cxbar .cxchip, .hb-msg .cxbar .cxnewbt")
    assert len(row) >= 6, row                                # 4 kinds + new chat + new group
    same_line = [b for b in row if abs((b[2] + b[1] / 2) - (stop + sh / 2)) <= 4]
    assert len(same_line) == len(row), f"the search took a row of its own: search top {stop}, tools {row}"
    bar_w = _boxes(page, ".hb-msg .cxbar")[0][0]
    assert sw < bar_w * 0.6, f"the search spans {sw}/{bar_w}px — it is a field with room around it, not a banner"
    # The new chat / new group buttons wear the header's icon scale.
    assert {(w, h) for w, h, _ in _boxes(page, ".hb-msg .cxbar .cxnewbt")} == {(_ICON, _ICON)}
