"""The REPLY flow (V2-051): apply_action('reply') → pending_reply → drain → bus msg.reply.

Channel-generic; exercised here with an email item. ("The only connector that can send today" stood in
this line until 2026-08-31 — V2-521 wired WhatsApp and Telegram to the same seam, each with its own drain
test in tests/browser/unit/mensajeria/test_a_dictated_reply_reaches_every_platform.py. This file keeps
covering the SHARED half: the queue and the topic, which all three platforms ride.)"""
import pytest

from widgets import store as wstore


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
