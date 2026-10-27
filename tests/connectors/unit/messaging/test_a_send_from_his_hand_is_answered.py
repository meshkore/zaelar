"""A send from his own hand in his own card is his order: it leaves, or the card says why not (V2-819).

Measured on a hosted engine (2026-10-27): in a WhatsApp chat the Send button emptied the box and the message never
reached WhatsApp nor the chat list. The send was TWO actions — `draft`, then a bare `send_draft {}` that sent «the
most recent draft», whichever conversation that was — the box was emptied the moment the order was queued, the
owner dropped what the action answered, the WhatsApp and Telegram reply drains told only the brain, and
`msg.send_failed` had publishers and no subscriber. So nothing after the click could reach the card.

Held here, with every connector MOCKED (nothing is ever sent for real):
  · the card's Send is ONE order with the box's text, naming its conversation, queued with a `ref`;
  · a send that cannot leave (platform not connected, nothing written, no conversation) is refused before it is
    queued, by the backed route's read-only veto, and its outbox row says why;
  · each of the three connectors' reply drains answers the outbox: an echo carrying the `ref` on success, a
    `msg.send_failed` carrying it on failure — and the owner settles the row either way.
"""
from __future__ import annotations

import asyncio
import queue
import time

import pytest

_CHAT = {"platform": "whatsapp", "chatId": "34600000001@s.whatsapp.net"}


@pytest.fixture
def box(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.mensajeria import data as md
    db = md.load_db()
    db["platforms"]["whatsapp"] = {"status": "connected"}
    db["platforms"]["telegram"] = {"status": "off"}
    db["active_chat"] = dict(_CHAT)
    store.save("mensajeria", db)
    return md


def _card(text="Llego en diez minutos", **over):
    return {"chat": dict(_CHAT), "ref": "c-test-1", "box_key": "c:whatsapp:" + _CHAT["chatId"], "text": text, **over}


def test_the_card_send_is_one_order_for_the_conversation_it_names(box):
    # A more recent draft for ANOTHER conversation exists: «the most recent draft» would be the wrong message.
    db = box.load_db()
    other = {"platform": "telegram", "chatId": "777"}
    box._drafts.write(db, other, "texto de otro chat", False)
    box.store.save("mensajeria", db)
    res = box.apply_action("send_draft", _card())
    assert res["ok"] is True and res["ref"] == "c-test-1", res
    rep = box.load_db()["pending_reply"][-1]
    assert rep["chatId"] == _CHAT["chatId"] and rep["text"] == "Llego en diez minutos" and rep["ref"] == "c-test-1"
    row = box.load_db()["outbox"][-1]
    assert row["state"] == "queued" and row["key"] == "c:whatsapp:" + _CHAT["chatId"]
    assert "texto de otro chat" in str(box.load_db()["drafts"]), "the other conversation's draft is untouched"


def test_a_platform_that_is_not_connected_refuses_before_queueing(box):
    payload = _card(chat={"platform": "telegram", "chatId": "777"})
    veto = box.answer_action("send_draft", payload)       # the door `widgets/server_api` calls
    assert veto and veto["ok"] is False and veto["error"] == "not_connected", veto
    res = box.apply_action("send_draft", payload)
    assert res["ok"] is False and not box.load_db().get("pending_reply")
    assert box.load_db()["outbox"][-1]["state"] == "failed", "the card's row says it did not leave"


def test_nothing_written_and_no_conversation_are_refused(box):
    assert box.apply_action("send_draft", _card(text="   "))["error"] == "empty"
    assert box.apply_action("send_draft", {"ref": "c-2", "text": "hola"})["error"] == "no_target"
    assert not box.load_db().get("pending_reply")


def test_a_voice_send_keeps_its_own_path(box):
    """No `ref` and no text: «envíalo» still sends the held draft (V2-800), untouched by the card's door."""
    from widgets.mensajeria import card_send
    assert not card_send.is_card_send({}) and not card_send.is_card_send({"contact": "Marta"})


def test_the_owner_settles_the_row_from_the_echo_and_from_the_failure(box):
    from widgets.mensajeria import owner, sent
    box.apply_action("send_draft", _card())
    box.apply_action("send_draft", _card(ref="c-test-2", text="otro"))
    o = owner._Owner()
    o._out_sub = type("S", (), {"queue": queue.Queue()})()
    o._failed_sub = type("S", (), {"queue": queue.Queue()})()
    o._out_sub.queue.put({**_CHAT, "messageId": "WA-OUT", "ref": "c-test-1", "body": "Llego en diez minutos"})
    o._failed_sub.queue.put({**_CHAT, "ref": "c-test-2", "reason": "Not connected to WhatsApp"})
    o._apply_outbound()
    o._apply_send_failures()
    rows = {r["ref"]: r for r in sent.outbox_view(box.load_db())}
    assert rows["c-test-1"]["state"] == "sent"
    assert rows["c-test-2"]["state"] == "failed" and "Not connected" in rows["c-test-2"]["reason"]
    # A late echo never turns a failure into a success.
    assert sent.outbox_settle(box.load_db(), "c-test-2", True) is False


def test_a_row_nobody_settles_is_shown_unconfirmed(box):
    from widgets.mensajeria import sent
    db = box.load_db()
    sent.outbox_queue(db, "c-old", "whatsapp", _CHAT["chatId"], "k", "hola")
    db["outbox"][-1]["at"] = time.time() - sent.OUTBOX_STALE_S - 5
    assert sent.outbox_view(db)[-1]["state"] == "unconfirmed"


# ── the three connectors' reply drains, MOCKED ───────────────────────────────────────────────────────────────
class _Inbox:
    def __init__(self, rows):
        self.rows = rows

    def drain(self):
        rows, self.rows = self.rows, []
        return rows


@pytest.fixture
def bus_calls(monkeypatch):
    from connectors.messaging import ingest
    calls = {"out": [], "failed": []}
    monkeypatch.setattr(ingest, "v2_enabled", lambda: True)
    monkeypatch.setattr(ingest, "publish_msg_out", lambda platform, m: calls["out"].append((platform, m)))
    monkeypatch.setattr(ingest, "publish_send_failed", lambda r, why: calls["failed"].append((r, why)))
    return calls


def _order(platform, chat_id):
    return {"platform": platform, "chatId": chat_id, "to": chat_id, "text": "hola", "ref": "c-drain",
            "attachments": [], "messageId": None}


@pytest.mark.parametrize("ok", [True, False])
def test_whatsapp_reply_drain_answers_the_card(monkeypatch, bus_calls, ok):
    from connectors.whatsapp import service as wa

    async def fake_send(chat_id, text, files, reply_to=None):
        if not ok:
            raise RuntimeError("POST /send → 503: Not connected to WhatsApp")
        return {"success": True, "messageId": "3EB0ABC"}
    monkeypatch.setattr(wa, "_send", fake_send)
    monkeypatch.setattr(wa, "_note", lambda *_a, **_k: None)
    monkeypatch.setattr(wa, "_reply_inbox", _Inbox([_order("whatsapp", _CHAT["chatId"])]))
    asyncio.run(wa._drain_replies())
    if ok:
        (_p, m), = bus_calls["out"]
        assert m["ref"] == "c-drain" and m["messageId"] == "3EB0ABC" and m["body"] == "hola"
        assert not bus_calls["failed"]
    else:
        (r, why), = bus_calls["failed"]
        assert r["ref"] == "c-drain" and "503" in why and not bus_calls["out"]


@pytest.mark.parametrize("ok", [True, False])
def test_telegram_reply_drain_answers_the_card(monkeypatch, bus_calls, ok):
    from connectors.telegram import service as tg

    async def fake_send(chat_id, text, files, reply_to=None):
        if not ok:
            raise RuntimeError("PeerIdInvalid")
        return type("M", (), {"id": 55, "date": None})()
    monkeypatch.setattr(tg, "_send", fake_send)
    monkeypatch.setattr(tg, "_note", lambda *_a, **_k: None)
    monkeypatch.setattr(tg, "_reply_inbox", _Inbox([_order("telegram", "777")]))
    asyncio.run(tg._drain_replies())
    if ok:
        (_p, m), = bus_calls["out"]
        assert m["ref"] == "c-drain" and m["messageId"] == "777:55"
    else:
        (r, why), = bus_calls["failed"]
        assert r["ref"] == "c-drain" and "PeerIdInvalid" in why


@pytest.mark.parametrize("ok", [True, False])
def test_email_reply_drain_answers_the_card(monkeypatch, bus_calls, ok):
    from connectors.email import config as ecfg
    from connectors.email import service as em
    monkeypatch.setattr(ecfg, "signature_lines", lambda: [])
    monkeypatch.setattr(em, "_reply_inbox", _Inbox([_order("email", "ana@example.com")]))

    class _MB:
        def send_reply(self, *a, **k):
            return (True, "") if ok else (False, "535 auth failed")

        def mark_seen(self, *_a):
            return None
    asyncio.run(em._drain_replies(_MB()))
    if ok:
        (_p, m), = bus_calls["out"]
        assert m["ref"] == "c-drain"
    else:
        (r, why), = bus_calls["failed"]
        assert r["ref"] == "c-drain" and "535" in why
