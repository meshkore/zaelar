"""The REPLY flow (V2-051): apply_action('reply') → pending_reply → drain → bus msg.reply.

Channel-generic; exercised here with an email item. ("The only connector that can send today" stood in
this line until 2026-08-31 — V2-521 wired WhatsApp and Telegram to the same seam, each with its own drain
test in tests/browser/unit/mensajeria/test_a_dictated_reply_reaches_every_platform.py. This file keeps
covering the SHARED half: the queue and the topic, which all three platforms ride.)"""
import pytest

from connectors.messaging import store as msgstore
from widgets import store as wstore
from widgets.mensajeria import data as mdata


@pytest.fixture
def isolated_store(monkeypatch):
    """Isolate the widget state file (same ID, same backend) so the real disk is not touched."""
    state = {}

    def _load(wid, default=None):
        return state.get(wid, default if default is not None else {})

    def _save(wid, db):
        state[wid] = db
        return db
    monkeypatch.setattr(wstore, "load", _load)
    monkeypatch.setattr(wstore, "save", _save)
    yield state


def _seed_email_item(**over):
    it = {"platform": "email", "messageId": "99", "chatId": "pablo@example.com",
          "senderId": "pablo@example.com", "from": "Pablo", "group": None, "isGroup": False,
          "body": "[Asunto: Cena] ¿Vienes?", "urgencia": "alta", "dirigido_a_mi": True, "motivo": "",
          "subject": "Cena", "msgid": "<abc@ex>"}
    it.update(over)
    return it


def test_reply_enqueues_pending_reply_with_threading(isolated_store, monkeypatch):
    # An email chat in the store (without dumping to memory: we short-circuit it)
    monkeypatch.setattr(msgstore, "_to_memory", lambda items: None)
    msgstore.upsert_items("email", [_seed_email_item()])

    # The operator replies to CHAT #1 (chat list, with no chat open)
    mdata.apply_action("reply", {"n": 1, "text": "Sí, allí estaré"})

    pending = msgstore.take_pending_reply("email")
    assert len(pending) == 1
    r = pending[0]
    assert r["platform"] == "email"
    assert r["to"] == "pablo@example.com"
    assert r["subject"] == "Cena"
    assert r["msgid"] == "<abc@ex>"           # correct threading
    assert r["text"] == "Sí, allí estaré"
    assert r["messageId"] == "99"             # UID to mark as read after sending


def test_reply_also_marks_read_and_removes_item(isolated_store, monkeypatch):
    monkeypatch.setattr(msgstore, "_to_memory", lambda items: None)
    msgstore.upsert_items("email", [_seed_email_item()])
    mdata.apply_action("reply", {"n": 1, "text": "vale"})
    # The replied-to item is removed from the list and its mark-read is queued
    assert not mdata.view_data()["items"]
    reads = msgstore.take_pending_read("email")
    assert any(k["messageId"] == "99" for k in reads)


def test_reply_ignored_without_text(isolated_store, monkeypatch):
    monkeypatch.setattr(msgstore, "_to_memory", lambda items: None)
    msgstore.upsert_items("email", [_seed_email_item()])
    mdata.apply_action("reply", {"n": 1, "text": "   "})
    assert not msgstore.take_pending_reply()   # nothing queued


def test_reply_inbox_filters_by_platform():
    """ReplyInbox('email') only consumes email msg.reply messages; it discards those from other platforms."""
    from connectors.messaging import ingest
    inbox = ingest.ReplyInbox("email")
    try:
        ingest.publish_reply({"platform": "email", "to": "a@x.com", "text": "hi"})
        ingest.publish_reply({"platform": "telegram", "to": "123", "text": "no"})
        got = inbox.drain()
        assert len(got) == 1 and got[0]["platform"] == "email"
    finally:
        inbox.close()
