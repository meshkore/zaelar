"""V2-683 row 2 — the three connectors OPENING a conversation, with faked transports.

`msg.reply` carries a `chatId` that exists because somebody already wrote. `msg.send` carries a HANDLE —
a username, a phone, an address — that the connector still has to turn into a conversation, and the id it
resolves exists NOWHERE ELSE. So the echo is not a nicety here: `connector.msg_out` carrying the order's
`ref` is the only way whatever asked for the send can learn which conversation it now owns.

The failure half matters as much: a send that cannot be made is reported ONCE and never retried, because a
message retried at a stranger is worse than a message not sent.
"""
from __future__ import annotations

import asyncio

import pytest

from connectors.messaging import ingest


class _Bus:
    """Captures what each connector publishes, by topic."""

    def __init__(self, monkeypatch):
        self.events: list[tuple[str, dict]] = []
        monkeypatch.setattr(ingest.bus, "emit_sync", lambda topic, payload=None:
                            self.events.append((topic, dict(payload or {}))))

    def of(self, topic: str) -> list[dict]:
        return [p for t, p in self.events if t == topic]


class _Inbox:
    """A `SendInbox` already holding one order — the connectors drain, they never subscribe here."""

    def __init__(self, *orders):
        self._orders = list(orders)

    def drain(self):
        out, self._orders = self._orders, []
        return out


_ORDER = {"ref": "s1-abc", "platform": "telegram", "to": "@ivanm", "chatId": "", "name": "Iván Petrenko",
          "contactId": "c1", "text": "Hola Iván, soy el asistente de Ricart."}


@pytest.fixture
def bus(monkeypatch):
    monkeypatch.setattr(ingest, "v2_enabled", lambda: True)
    return _Bus(monkeypatch)


# ── Telegram: the handle has to be RESOLVED, and the id comes back ───────────────────────────────────────

def test_telegram_sends_by_handle_and_echoes_the_id_it_resolved(bus, monkeypatch):
    from connectors.telegram import service as tg

    sent = {}

    class _Msg:
        id = 77
        chat_id = -100999

        class date:
            @staticmethod
            def timestamp():
                return 1757700000.0

    async def _send(peer, text, **kw):
        sent["peer"], sent["text"], sent["kw"] = peer, text, kw
        return _Msg()

    monkeypatch.setattr(tg, "_send_inbox", _Inbox(dict(_ORDER)))
    monkeypatch.setattr(tg, "_client", type("C", (), {"send_message": staticmethod(_send)})())
    asyncio.run(tg._drain_sends())

    assert sent["peer"] == "@ivanm", "a handle must reach Telethon as a STRING for it to resolve"
    # V2-693 — and VERBATIM: Telethon's default is markdown, which eats `_` and hands Telegram its own
    # entities, and a message that arrives with entities is one Telegram does not auto-link. The operator
    # measured it on a Meet link that arrived unclickable.
    assert sent["kw"].get("parse_mode", "md") is None
    out = bus.of(ingest.TOPIC_MSG_OUT)
    assert len(out) == 1
    assert out[0]["ref"] == "s1-abc"
    assert out[0]["chatId"] == -100999, "the id only exists because Telegram resolved it"


# ── WhatsApp: a number IS the address ────────────────────────────────────────────────────────────────────

def test_whatsapp_turns_the_phone_into_the_id_its_own_messages_carry(bus, monkeypatch):
    from connectors.whatsapp import service as wa
    sent = {}

    async def _send(chat_id, text, reply_to=None):
        sent["chatId"] = chat_id
        return {"messageId": "wa-9"}

    monkeypatch.setattr(wa, "_send_inbox", _Inbox({**_ORDER, "platform": "whatsapp",
                                                   "to": "+34 600 111 222"}))
    monkeypatch.setattr(wa.client, "send_message", _send)
    asyncio.run(wa._drain_sends())

    assert sent["chatId"] == "34600111222@s.whatsapp.net"
    out = bus.of(ingest.TOPIC_MSG_OUT)
    assert out and out[0]["ref"] == "s1-abc" and out[0]["chatId"] == "34600111222@s.whatsapp.net"


# ── Email: a first message is not a «Re:» ────────────────────────────────────────────────────────────────

def test_email_sends_with_its_OWN_subject_and_no_threading(bus, monkeypatch):
    from connectors.email import service as em
    sent = {}

    class _MB:
        @staticmethod
        def send_message(to, subject, body, attachments=None):
            # a first message is a NEW mail: no thread to continue, so nothing to thread on (2026-09-28: it went
            # out through send_reply as «Re: Hola»)
            sent.update({"to": to, "subject": subject, "body": body, "in_reply_to": ""})
            return True, "<newid@x>"

    monkeypatch.setattr(em, "_send_inbox", _Inbox({**_ORDER, "platform": "email", "to": "ivan@example.com",
                                                   "subject": "Una reunión esta tarde"}))
    monkeypatch.setattr(em.config, "signature_lines", lambda: [])
    asyncio.run(em._drain_sends(_MB()))

    assert sent["to"] == "ivan@example.com"
    assert sent["subject"] == "Una reunión esta tarde"
    assert sent["in_reply_to"] == "", "there is no thread to continue: this message STARTS one"
    out = bus.of(ingest.TOPIC_MSG_OUT)
    assert out and out[0]["ref"] == "s1-abc" and out[0]["chatId"] == "ivan@example.com"


def test_email_falls_back_to_a_subject_rather_than_sending_none(bus, monkeypatch):
    from connectors.email import service as em
    sent = {}

    class _MB:
        @staticmethod
        def send_message(to, subject, body, attachments=None):
            sent["subject"] = subject
            return True, "<id>"

    monkeypatch.setattr(em, "_send_inbox", _Inbox({**_ORDER, "platform": "email", "to": "ivan@example.com"}))
    monkeypatch.setattr(em.config, "signature_lines", lambda: [])
    asyncio.run(em._drain_sends(_MB()))
    assert sent["subject"].strip()


def test_email_reports_a_failed_send(bus, monkeypatch):
    from connectors.email import service as em

    class _MB:
        @staticmethod
        def send_message(to, subject, body, attachments=None):
            return False, "mailbox unavailable"

    monkeypatch.setattr(em, "_send_inbox", _Inbox({**_ORDER, "platform": "email", "to": "ivan@example.com"}))
    monkeypatch.setattr(em.config, "signature_lines", lambda: [])
    asyncio.run(em._drain_sends(_MB()))
    assert bus.of(ingest.TOPIC_SEND_FAILED)
    assert bus.of(ingest.TOPIC_MSG_OUT) == []


# ── the queue itself ─────────────────────────────────────────────────────────────────────────────────────

def test_taking_an_order_REMOVES_it(monkeypatch):
    """Everything here is at-most-once by construction: a queue that is read without emptying sends twice."""
    from connectors.messaging import store as msgstore
    state = {}
    monkeypatch.setattr(msgstore._wstore(), "load", lambda wid, d=None: state.get(wid, d or {}))
    monkeypatch.setattr(msgstore._wstore(), "save", lambda wid, db: state.__setitem__(wid, db) or db)
    db = msgstore.load()
    db["pending_send"] = [dict(_ORDER), {**_ORDER, "platform": "email", "ref": "s2"}]
    msgstore.save(db)

    assert [o["ref"] for o in msgstore.take_pending_send("telegram")] == ["s1-abc"]
    assert [o["ref"] for o in msgstore.take_pending_send("telegram")] == []
    assert [o["ref"] for o in msgstore.take_pending_send()] == ["s2"]
