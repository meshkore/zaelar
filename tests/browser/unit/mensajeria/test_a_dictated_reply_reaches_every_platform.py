"""A dictated reply reaches EVERY platform, not just email (V2-521).

The operator dictates a reply (or asks the brain to compose one) and the bot sends it — through the
CONFIRM gate, always. The seam existed since V2-051: the widget enqueues into `msg.reply` on the bus and
"that platform's connector drains and SENDS". Only the email connector ever subscribed; the WhatsApp
bridge has had `POST /send` all along and Telethon sends in one line, but nobody drained the topic — so
"contesta a este por WhatsApp" produced a confirmed, enqueued reply that no one would ever deliver.

Failure policy, deliberate and shared with email: a failed send is TOLD to the operator (brain_notes)
and not requeued — one honest "no pude enviarlo" beats a bad send retried forever.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

MANIFEST = Path(__file__).resolve().parents[4] / "widgets" / "mensajeria" / "manifest.json"


class _Inbox:
    def __init__(self, items):
        self._items = list(items)

    def drain(self):
        out, self._items = self._items, []
        return out


def test_whatsapp_sends_through_the_bridge(monkeypatch):
    from connectors.whatsapp import client, service
    from connectors.messaging import ingest
    sent, notes = [], []
    monkeypatch.setattr(ingest, "v2_enabled", lambda: True)
    monkeypatch.setattr(service, "_reply_inbox",
                        _Inbox([{"chatId": "34600@s.whatsapp.net", "to": "Marta",
                                 "messageId": "ABC1", "text": "el sábado me va genial"}]))
    async def fake_send(chat_id, text, reply_to=None):
        sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to})
        return {"success": True}
    monkeypatch.setattr(client, "send_message", fake_send)
    monkeypatch.setattr(service, "_note", notes.append)
    asyncio.run(service._drain_replies())
    assert sent == [{"chat_id": "34600@s.whatsapp.net", "text": "el sábado me va genial", "reply_to": "ABC1"}]
    assert notes and "enviado" in notes[0].lower()


def test_telegram_sends_through_telethon(monkeypatch):
    from connectors.telegram import service
    from connectors.messaging import ingest
    sent, notes = [], []
    monkeypatch.setattr(ingest, "v2_enabled", lambda: True)
    monkeypatch.setattr(service, "_reply_inbox",
                        _Inbox([{"chatId": "777", "messageId": "42", "to": "Luis", "text": "hecho"}]))
    class _TG:
        async def send_message(self, chat_id, text, reply_to=None):
            sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to})
    monkeypatch.setattr(service, "_client", _TG())
    monkeypatch.setattr(service, "_note", notes.append)
    asyncio.run(service._drain_replies())
    assert sent == [{"chat_id": 777, "text": "hecho", "reply_to": 42}]
    assert notes and "enviado" in notes[0].lower()


def test_a_failed_send_is_told_not_swallowed_and_not_looped(monkeypatch):
    from connectors.whatsapp import client, service
    from connectors.messaging import ingest
    notes, republished = [], []
    monkeypatch.setattr(ingest, "v2_enabled", lambda: True)
    monkeypatch.setattr(ingest, "publish_reply", republished.append, raising=False)
    inbox = _Inbox([{"chatId": "x@s.whatsapp.net", "to": "Ana", "text": "hola"}])
    monkeypatch.setattr(service, "_reply_inbox", inbox)
    async def boom(chat_id, text, reply_to=None):
        raise client.BridgeError("Not connected to WhatsApp")
    monkeypatch.setattr(client, "send_message", boom)
    monkeypatch.setattr(service, "_note", notes.append)
    asyncio.run(service._drain_replies())
    assert notes and "no se pudo" in notes[0].lower()      # the operator is TOLD…
    assert not republished and not inbox._items            # …and nothing loops forever


def test_the_manifest_no_longer_claims_email_only():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    desc = m["actions"]["reply"]["desc"].lower()
    assert "whatsapp" in desc and "telegram" in desc
    assert "hoy email" not in desc
    assert m["actions"]["reply"].get("confirm") is True    # dictating is guided; SENDING still asks first
