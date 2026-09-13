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


_ORDER = {"ref": "s1-abc", "platform": "telegram", "to": "@ivanm", "chatId": "", "name": "Iván Musikin",
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

    async def _send(peer, text):
        sent["peer"], sent["text"] = peer, text
        return _Msg()

    monkeypatch.setattr(tg, "_send_inbox", _Inbox(dict(_ORDER)))
    monkeypatch.setattr(tg, "_client", type("C", (), {"send_message": staticmethod(_send)})())
    asyncio.run(tg._drain_sends())

    assert sent["peer"] == "@ivanm", "a handle must reach Telethon as a STRING for it to resolve"
    out = bus.of(ingest.TOPIC_MSG_OUT)
    assert len(out) == 1
    assert out[0]["ref"] == "s1-abc"
    assert out[0]["chatId"] == -100999, "the id only exists because Telegram resolved it"


@pytest.mark.parametrize("chat_id,expected", [
    ("4242", 4242),      # a NUMERIC id IS the conversation: re-resolving the handle is a second chance to err
    ("-100999", -100999),                      # a group/channel id is negative
    ("", "@ivanm"),                            # nothing yet: the handle is all there is
    ("no-es-un-numero", "@ivanm"),             # free-form text in the queue must never crash the drain
])
def test_telegram_addresses_by_the_id_only_when_it_IS_one(bus, monkeypatch, chat_id, expected):
    """The queue's `chatId` is free-form (it comes from a store, not from Telegram), so «is this a number»
    has to be asked before using it as one. `int()` on the rest raises INSIDE the send, which reports a
    failure for a message that was never even attempted."""
    from connectors.telegram import service as tg
    seen = {}

    async def _send(peer, text):
        seen["peer"] = peer
        return type("M", (), {"id": 1, "chat_id": 4242, "date": None})()

    monkeypatch.setattr(tg, "_send_inbox", _Inbox({**_ORDER, "chatId": chat_id}))
    monkeypatch.setattr(tg, "_client", type("C", (), {"send_message": staticmethod(_send)})())
    monkeypatch.setattr(tg, "_note", lambda t: None)
    asyncio.run(tg._drain_sends())
    assert seen.get("peer") == expected
    assert bus.of(ingest.TOPIC_SEND_FAILED) == []


def test_telegram_reports_a_refusal_once_and_does_not_retry(bus, monkeypatch):
    """A phone that is not in the account's contacts raises. Saying so once is the honest answer."""
    from connectors.telegram import service as tg
    calls = {"n": 0}

    async def _boom(peer, text):
        calls["n"] += 1
        raise ValueError("Cannot find any entity corresponding to '+34600111222'")

    notes = []
    monkeypatch.setattr(tg, "_send_inbox", _Inbox({**_ORDER, "to": "+34600111222"}))
    monkeypatch.setattr(tg, "_client", type("C", (), {"send_message": staticmethod(_boom)})())
    monkeypatch.setattr(tg, "_note", lambda t: notes.append(t))
    asyncio.run(tg._drain_sends())

    assert calls["n"] == 1
    assert bus.of(ingest.TOPIC_MSG_OUT) == [], "nothing was sent, so nothing joins the conversation"
    failed = bus.of(ingest.TOPIC_SEND_FAILED)
    assert len(failed) == 1 and failed[0]["ref"] == "s1-abc"
    assert notes and "Iván Musikin" in notes[0]


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


def test_whatsapp_says_the_number_may_not_have_whatsapp(bus, monkeypatch):
    from connectors.whatsapp import service as wa

    async def _boom(chat_id, text, reply_to=None):
        raise RuntimeError("not-on-whatsapp")

    notes = []
    monkeypatch.setattr(wa, "_send_inbox", _Inbox({**_ORDER, "platform": "whatsapp", "to": "34600111222"}))
    monkeypatch.setattr(wa.client, "send_message", _boom)
    monkeypatch.setattr(wa, "_note", lambda t: notes.append(t))
    asyncio.run(wa._drain_sends())

    assert bus.of(ingest.TOPIC_SEND_FAILED)
    assert notes and "WhatsApp" in notes[0]


# ── Email: a first message is not a «Re:» ────────────────────────────────────────────────────────────────

def test_email_sends_with_its_OWN_subject_and_no_threading(bus, monkeypatch):
    from connectors.email import service as em
    sent = {}

    class _MB:
        @staticmethod
        def send_reply(to, subject, body, in_reply_to="", cc=None):
            sent.update({"to": to, "subject": subject, "body": body, "in_reply_to": in_reply_to})
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
        def send_reply(to, subject, body, in_reply_to="", cc=None):
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
        def send_reply(to, subject, body, in_reply_to="", cc=None):
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
