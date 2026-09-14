"""V2-693 — what leaves this door is TEXT, not markup, and a URL in it has to be tappable.

The operator measured it on the Meet link the errand had just minted: «el mensaje se ha enviado pero el
enlace no es clicable… sí que sale el embedding conforme ha reconocido el link, pero no es clicable».

The cause is a default. Telethon parses outgoing messages as MARKDOWN unless told otherwise: it consumes
`_`, `*` and backticks as formatting and hands Telegram its own entity list — and a message that arrives
carrying entities is one Telegram does not run its URL auto-detection over. Everything this connector sends
is prose a model wrote for a human. An underscore in it is an underscore, and a link in it is a link.
"""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("telethon")

from connectors.telegram import service


class _Client:
    def __init__(self):
        self.calls = []

    async def send_message(self, peer, text, **kw):
        self.calls.append({"peer": peer, "text": text, **kw})
        return type("S", (), {"id": 1, "chat_id": 123, "date": None})()


class _Inbox:
    def __init__(self, rows):
        self._rows = rows

    def drain(self):
        rows, self._rows = self._rows, []
        return rows


@pytest.fixture
def tg(monkeypatch):
    cli = _Client()
    monkeypatch.setattr(service, "_client", cli)
    monkeypatch.setattr(service.ingest, "v2_enabled", lambda: True)
    return cli


def test_a_first_message_is_sent_VERBATIM(tg, monkeypatch):
    monkeypatch.setattr(service, "_send_inbox", _Inbox([
        {"ref": "r1", "to": "@alguien", "chatId": "", "name": "Alguien",
         "text": "Nos vemos el martes.\n\nhttps://meet.google.com/erp-tuzi-gog"}]))
    monkeypatch.setattr(service.ingest, "publish_msg_out", lambda *a, **k: None)

    asyncio.run(service._drain_sends())

    assert len(tg.calls) == 1
    assert tg.calls[0]["parse_mode"] is None, \
        "markdown parsing is what made the URL arrive as unclickable text"
    assert tg.calls[0]["text"].endswith("https://meet.google.com/erp-tuzi-gog")


def test_an_underscore_in_a_name_is_not_formatting(tg, monkeypatch):
    """The same default silently ate `_` from real text — a handle or a filename is not italics."""
    monkeypatch.setattr(service, "_send_inbox", _Inbox([
        {"ref": "r2", "to": "@x", "chatId": "", "name": "X",
         "text": "Escríbele a @cryptonite_fund y a @otro_usuario."}]))
    monkeypatch.setattr(service.ingest, "publish_msg_out", lambda *a, **k: None)

    asyncio.run(service._drain_sends())

    assert tg.calls[0]["parse_mode"] is None
    assert tg.calls[0]["text"] == "Escríbele a @cryptonite_fund y a @otro_usuario."
