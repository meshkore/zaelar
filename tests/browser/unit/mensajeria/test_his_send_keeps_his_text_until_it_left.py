"""The card's Send keeps his text until the message LEFT, and says why when it did not (RENDERED, V2-819).

Measured on a hosted engine (2026-10-27): in a WhatsApp chat, Send emptied the box and the message never reached
WhatsApp. The box was emptied the moment the order was queued — before anything was known — and the send was two
actions, the second of which sent «the most recent draft». Now the button fires ONE order with the box's text and
its conversation, the box stays (locked, «Sending…») until the order's outbox row says «sent», and a refusal or a
failure gives his text back with the reason. The server side is held in
`tests/connectors/unit/messaging/test_a_send_from_his_hand_is_answered.py`.
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
_HOST = """<!doctype html><html><head><meta charset="utf-8"></head><body>
  <div style="width:620px;height:560px;display:flex;flex-direction:column"><div style="flex:1;min-height:0;overflow:auto">
  <div id="w"></div></div></div></body></html>"""
_A = "34600000001@s.whatsapp.net"
_KEY = "c:whatsapp:" + _A


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


def _data(outbox=None):
    return {"platforms": {"whatsapp": {"status": "connected"}}, "items": [], "chats": [],
            "active_chat": {"platform": "whatsapp", "chatId": _A},
            "active_items": [{"platform": "whatsapp", "chatId": _A, "messageId": "W1", "from": "Marta",
                              "dir": "in", "body": "¿Vienes?", "ts": 1761500000}],
            "thread_meta": {"count": 1, "complete": True, "isGroup": False, "name": "Marta"},
            "muted_channels": [], "draft": None, "drafts": {}, "sent": [], "outbox": outbox or []}


def _mount(page, answer):
    """`answer` is what the action door gives back: the backed route's queued ack, a refusal, or nothing."""
    page.goto(page._hb_origin)
    page.set_content(_HOST)
    page.evaluate(
        """async ([src, data, answer]) => {
             window.__calls = [];
             window.__mod = await import(src);
             window.__ctx = { action: (name, payload) => { window.__calls.push([name, payload || {}]);
                                                            return Promise.resolve(answer); },
                              top: () => {}, openConnector: () => {}, running: true };
             window.__mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_widget_url, _data(), answer],
    )


def _repaint(page, data):
    page.evaluate("data => window.__mod.render(document.getElementById('w'), data, window.__ctx)", data)


def _send(page, text):
    box = page.locator(".composebox")
    box.click()
    box.fill(text)
    page.locator(".composeside .bt-primary").click()


def _sends(page):
    return [c[1] for c in page.evaluate("window.__calls") if c[0] == "send_draft"]


def test_one_order_names_the_conversation_and_the_box_waits_for_the_outcome(_page):
    _mount(_page, {"ok": True, "queued": True})
    _send(_page, "Sí, voy")
    _page.wait_for_function("() => window.__calls.some(c => c[0] === 'send_draft')", timeout=5000)
    (order,) = _sends(_page)
    assert order["text"] == "Sí, voy" and order["chat"] == {"platform": "whatsapp", "chatId": _A}, order
    assert order["ref"] and order["box_key"] == _KEY
    assert not [c for c in _page.evaluate("window.__calls") if c[0] == "draft"], "one order, not draft + send"
    box = _page.locator(".composebox")
    assert box.input_value() == "Sí, voy" and box.get_attribute("readonly") is not None, "kept until it left"
    assert "Enviando" in _page.locator(".composeside .bt-primary").inner_text()
    _repaint(_page, _data(outbox=[{"ref": order["ref"], "state": "sent", "platform": "whatsapp"}]))
    assert _page.locator(".composebox").input_value() == "", "it left: now the box empties"
    assert _page.locator(".composeerr").count() == 0


def test_a_connector_failure_gives_his_text_back_with_the_reason(_page):
    _mount(_page, {"ok": True, "queued": True})
    _send(_page, "Sí, voy")
    _page.wait_for_function("() => window.__calls.some(c => c[0] === 'send_draft')", timeout=5000)
    ref = _sends(_page)[0]["ref"]
    _repaint(_page, _data(outbox=[{"ref": ref, "state": "failed", "platform": "whatsapp",
                                   "reason": "Not connected to WhatsApp"}]))
    box = _page.locator(".composebox")
    assert box.input_value() == "Sí, voy" and box.get_attribute("readonly") is None
    assert "Not connected to WhatsApp" in _page.locator(".composeerr").inner_text()


def test_a_refusal_keeps_the_text_and_says_it_in_his_words(_page):
    _mount(_page, {"ok": False, "error": "not_connected", "message": "x"})
    _send(_page, "Sí, voy")
    _page.wait_for_selector(".composeerr", timeout=5000)
    assert "WhatsApp" in _page.locator(".composeerr").inner_text()
    assert _page.locator(".composebox").input_value() == "Sí, voy"


def test_an_agent_that_does_not_answer_is_not_a_send(_page):
    _mount(_page, None)
    _send(_page, "Sí, voy")
    _page.wait_for_selector(".composeerr", timeout=5000)
    assert _page.locator(".composebox").input_value() == "Sí, voy"


def test_an_unconfirmed_send_says_so_and_does_not_claim_it_failed(_page):
    _mount(_page, {"ok": True, "queued": True})
    _send(_page, "Sí, voy")
    _page.wait_for_function("() => window.__calls.some(c => c[0] === 'send_draft')", timeout=5000)
    ref = _sends(_page)[0]["ref"]
    _repaint(_page, _data(outbox=[{"ref": ref, "state": "unconfirmed", "platform": "whatsapp"}]))
    assert "confirmado" in _page.locator(".composeerr").inner_text()
    assert _page.locator(".composebox").input_value() == "Sí, voy"
