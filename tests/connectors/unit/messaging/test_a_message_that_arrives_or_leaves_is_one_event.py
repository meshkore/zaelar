"""A message that arrives, and a send the connector made, are one observer row each (capture gaps, 2026-11-06).

What came in by email, WhatsApp or Telegram left no event at the moment it arrived (only the pulse's `notify 🔔`
later), and a send left a card op — the connector call itself, with its result, was nowhere. Now `ingest.publish_msg`
(the one door every connector's inbound crosses) records `connector · 📨 <platform>` with sender, subject and a
bounded excerpt, and the one network seam of each connector (SMTP `_deliver`, the WhatsApp bridge `_send`, Telethon
`_send`) records `connector · 📤 <platform> · reply|send` with ok, ms, the handle and the failure's cause.

Disarm: remove the `calls.inbound` line from `publish_msg`, or the `calls.sent` pair from any seam → red.
"""
from __future__ import annotations

import asyncio
from email.message import EmailMessage
from types import SimpleNamespace

import pytest

import bus
from connectors.messaging import calls, ingest


@pytest.fixture
def rows(monkeypatch):
    bus.reset()
    out: list[dict] = []
    import voice.observer as obs

    def fake_emit(kind, label, text="", role="", extra=None, piece=None):
        out.append({"kind": kind, "label": label, "text": text, "role": role, **(extra or {}),
                    **({"piece": piece} if piece else {})})
    monkeypatch.setattr(obs, "emit", fake_emit)
    yield out
    bus.reset()


def test_an_inbound_message_is_one_row_with_sender_subject_and_a_bounded_excerpt(rows):
    body = "Hola, te paso la factura de octubre. " * 20
    ingest.publish_msg("email", {"messageId": "m1", "chatId": "ana@example.org", "senderName": "Ana",
                                 "subject": "Factura octubre", "body": body, "attachments": ["a.pdf"],
                                 "password": "never-here"})
    assert len(rows) == 1
    r = rows[0]
    assert (r["kind"], r["label"], r["platform"], r["op"]) == ("connector", "📨 email", "email", "inbound")
    assert r["from"] == "Ana" and r["subject"] == "Factura octubre" and r["message_id"] == "m1"
    assert r["attachments"] == 1 and r["group"] is False
    assert r["text"].startswith("Hola, te paso") and len(r["text"]) <= calls.EXCERPT < len(body)
    assert "body" not in r and "password" not in r, "only the bounded excerpt and the headers travel"


def test_a_group_message_names_its_chat_and_a_feed_leaves_nothing(rows):
    ingest.publish_msg("whatsapp", {"messageId": "w1", "chatId": "1@g.us", "senderName": "Luis", "chatName": "Familia",
                                    "isGroup": True, "body": "hola"})
    ingest.publish_msg("whatsapp", {"messageId": "w2", "chatId": "status@broadcast", "body": "a status"})
    assert [r["label"] for r in rows] == ["📨 whatsapp"]
    assert rows[0]["chat"] == "Familia" and rows[0]["group"] is True


def test_the_email_seam_records_a_reply_that_left_and_a_send_that_did_not(rows, monkeypatch):
    from connectors.email.mailbox import smtp

    class _Smtp:
        def send_message(self, msg): pass
        def quit(self): pass
    ok_self = SimpleNamespace(_connect_smtp=lambda: _Smtp(), _smtp_login=lambda s: None)
    msg = EmailMessage(); msg["To"] = "ana@example.org"; msg["In-Reply-To"] = "<x@y>"
    assert smtp._SmtpMixin._deliver(ok_self, msg, "<id>") == (True, "<id>")

    def _refuse():
        raise ConnectionRefusedError("smtp down")
    bad_self = SimpleNamespace(_connect_smtp=_refuse, _smtp_login=lambda s: None)
    msg2 = EmailMessage(); msg2["To"] = "luis@example.org"
    ok, info = smtp._SmtpMixin._deliver(bad_self, msg2, "<id2>")
    assert ok is False and "smtp down" in info
    a, b = rows
    assert (a["label"], a["op"], a["ok"], a["to"]) == ("📤 email · reply · ✅", "reply", True, "ana@example.org")
    assert (b["label"], b["op"], b["ok"], b["to"]) == ("📤 email · send · ⚠️", "send", False, "luis@example.org")
    assert "ConnectionRefusedError" in b["error"] and isinstance(b["ms"], int)


def test_the_whatsapp_seam_records_the_bridge_call_and_its_real_cause(rows, monkeypatch):
    from connectors.whatsapp import client
    from connectors.whatsapp.service import outbound

    async def send_ok(chat_id, text, reply_to=None):
        return {"messageId": "wa-1"}
    monkeypatch.setattr(client, "send_message", send_ok)
    assert asyncio.run(outbound._send("34600@s.whatsapp.net", "hola", [], reply_to="m9")) == {"messageId": "wa-1"}

    async def send_bad(chat_id, text, reply_to=None):
        raise client.BridgeError("bridge", status=503, error="not connected")
    monkeypatch.setattr(client, "send_message", send_bad)
    with pytest.raises(client.BridgeError):
        asyncio.run(outbound._send("34600@s.whatsapp.net", "hola", []))
    a, b = rows
    assert (a["platform"], a["op"], a["ok"], a["to"]) == ("whatsapp", "reply", True, "34600@s.whatsapp.net")
    assert (b["op"], b["ok"], b["error"]) == ("send", False, "not connected")


def test_the_telegram_seam_records_the_telethon_call(rows, monkeypatch):
    from connectors.telegram import service as _svc        # the facade first: it binds account_ops
    from connectors.telegram import account_ops

    async def send_message(peer, text, reply_to=None, parse_mode=None):
        return SimpleNamespace(id=5, chat_id=peer)
    monkeypatch.setattr(_svc, "_client", SimpleNamespace(send_message=send_message))
    sent = asyncio.run(account_ops._send(123, "hola", []))
    assert sent.id == 5
    assert rows[0]["label"] == "📤 telegram · send · ✅" and rows[0]["to"] == "123" and rows[0]["ok"] is True


def test_a_record_that_fails_never_takes_the_message_with_it(monkeypatch):
    import voice.observer as obs

    def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(obs, "emit", boom)
    calls.inbound("email", {"body": "x"})
    calls.sent("email", "send", ok=True, ms=1)
    bus.reset()
    sub = bus.subscribe(ingest.TOPIC_MSG)
    ingest.publish_msg("telegram", {"messageId": "m1", "body": "hola"})
    assert sub.queue.get_nowait()["messageId"] == "m1"
    bus.reset()
