"""An open chat stays where he is: it opens on its latest message, and a repaint never moves him (RENDERED, V2-819).

The operator, in a WhatsApp chat on the desktop: he scrolled to the latest message, started typing, and the
conversation jumped up and the box lost its focus. The host repaints the card on EVERY store write, and the card
writes the store itself while he types (the composer's autosave); each repaint rebuilt the thread from nothing —
the list back at its top, the box unfocused. And a chat opened at its OLDEST message.

Rendered in a real browser from the real widget module; the host's repaint is `render()` called again with the
data a store write would bring (a draft echo, a new message), exactly what `desktop.js refreshData` does.
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys

import pytest
from tests.waiting import port_listening

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]

_HOST = """<!doctype html><html><head><meta charset="utf-8"><style>
  body{margin:0;padding:20px;font-family:-apple-system,system-ui,sans-serif}
  .hb-win{position:relative;background:#fff;border:1px solid #e3e8f0;border-radius:16px;
          padding:30px 16px 16px;overflow:hidden;display:flex;flex-direction:column;
          width:620px;height:560px;box-sizing:border-box}
  .hb-scroll{flex:1 1 auto;min-height:0;overflow:auto}
</style></head><body>
  <div class="hb-win"><div class="hb-scroll"><div id="w"></div></div></div>
</body></html>"""

_A = "34600000001@s.whatsapp.net"
_B = "34600000002@s.whatsapp.net"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def _page():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_listening(port)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 760, "height": 700})
            page._hb_widget_url = f"http://127.0.0.1:{port}/widgets/mensajeria/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/mensajeria/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _msgs(chat, n, start=0):
    return [{"platform": "whatsapp", "chatId": chat, "messageId": f"{chat[:4]}-{i}", "from": "Marta",
             "dir": "out" if i % 3 == 0 else "in", "body": f"mensaje número {i} de la conversación",
             "ts": 1761500000 + i * 60} for i in range(start, start + n)]


def _data(chat=_A, n=40, **extra):
    d = {"platforms": {"whatsapp": {"status": "connected"}}, "items": [], "chats": [],
         "active_chat": {"platform": "whatsapp", "chatId": chat}, "active_items": _msgs(chat, n),
         "thread_meta": {"count": n, "complete": True, "isGroup": False, "name": "Marta"},
         "muted_channels": [], "draft": None, "drafts": {}, "sent": [], "outbox": []}
    d.update(extra)
    return d


def _mount(page, data):
    page.goto(page._hb_origin)
    page.set_content(_HOST)
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             window.__mod = await import(src);
             window.__ctx = { action: (name, payload) => { window.__calls.push([name, payload || {}]);
                                                            return Promise.resolve({ok: true, queued: true}); },
                              top: () => {}, openConnector: () => {}, running: true };
             window.__mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_widget_url, data],
    )


def _repaint(page, data):
    """What the host does on a store write: the SAME card, `render()` again with the fresh data."""
    page.evaluate("data => window.__mod.render(document.getElementById('w'), data, window.__ctx)", data)


def _gap_to_bottom(page):
    return page.evaluate("""() => { const l = document.querySelector('.thread > .tl');
                                    return l.scrollHeight - l.scrollTop - l.clientHeight; }""")


def _wait_at_bottom(page):
    page.wait_for_function("""() => { const l = document.querySelector('.thread > .tl');
                                      return l && l.scrollHeight > l.clientHeight
                                             && l.scrollHeight - l.scrollTop - l.clientHeight <= 2; }""",
                           timeout=5000)


def test_a_chat_opens_on_its_latest_message(_page):
    _mount(_page, _data())
    _wait_at_bottom(_page)
    assert _page.locator(".tbrow").last.is_visible()


def test_typing_keeps_the_focus_the_caret_and_the_bottom_through_every_repaint(_page):
    _mount(_page, _data())
    _wait_at_bottom(_page)
    box = _page.locator(".composebox")
    box.click()
    box.type("Llego en diez min")
    # The autosave's own echo, then a new message arriving while he writes — two repaints of the same chat.
    key = "c:whatsapp:" + _A
    echo = _data(drafts={key: {"key": key, "text": "Llego en diez min", "target": {"platform": "whatsapp",
                                                                                     "chatId": _A}}})
    _repaint(_page, echo)
    _repaint(_page, _data(n=41))
    state = _page.evaluate("""() => { const a = document.activeElement;
        return {cls: a && a.className, value: a && a.value, caret: a && a.selectionStart}; }""")
    assert state["cls"] == "composebox", state
    assert state["value"] == "Llego en diez min" and state["caret"] == len("Llego en diez min"), state
    box.type("utos")
    assert box.input_value() == "Llego en diez minutos", "his next keys land in the box, not nowhere"
    _wait_at_bottom(_page)
    assert "número 40" in _page.locator(".tbrow").last.inner_text(), "the new message is in view"


def test_reading_further_up_a_repaint_keeps_the_same_message_in_place(_page):
    _mount(_page, _data())
    _wait_at_bottom(_page)
    _page.evaluate("() => { const l = document.querySelector('.thread > .tl'); l.scrollTop = 200; }")
    before = _page.evaluate("""() => { const l = document.querySelector('.thread > .tl');
        const top = l.getBoundingClientRect().top;
        const r = Array.from(l.querySelectorAll('[data-row-key]')).find(x => x.getBoundingClientRect().bottom > top);
        return {key: r.dataset.rowKey, off: r.getBoundingClientRect().top - top}; }""")
    _repaint(_page, _data(n=42))
    after = _page.evaluate("""key => { const l = document.querySelector('.thread > .tl');
        const r = Array.from(l.querySelectorAll('[data-row-key]')).find(x => x.dataset.rowKey === key);
        return r.getBoundingClientRect().top - l.getBoundingClientRect().top; }""", before["key"])
    assert abs(after - before["off"]) <= 2, (before, after)
    assert _gap_to_bottom(_page) > 50, "he was reading further up; a new message does not drag him down"


def test_another_chat_opens_on_its_own_latest_message(_page):
    _mount(_page, _data())
    _wait_at_bottom(_page)
    _page.evaluate("() => { document.querySelector('.thread > .tl').scrollTop = 0; }")
    _repaint(_page, _data(chat=_B, n=30))
    _wait_at_bottom(_page)


def test_the_chat_list_search_keeps_its_focus_through_a_repaint(_page):
    lens = {"rows": [{"chatId": _A, "name": "Marta", "ts": 1761500000, "preview": "hola"}], "asked": True}
    d = _data(active_chat=None, chat_list={"whatsapp": lens}, view={"platform": "whatsapp", "n": 7, "at": 0})
    _mount(_page, d)
    s = _page.locator(".cxsearch")
    s.click()
    s.type("Mar")
    _repaint(_page, d)
    assert _page.evaluate("() => document.activeElement && document.activeElement.className") == "cxsearch"
    assert _page.locator(".cxsearch").input_value() == "Mar"
