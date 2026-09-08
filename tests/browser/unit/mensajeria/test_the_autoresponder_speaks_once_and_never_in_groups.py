"""V2-624 — the autoresponder: the «Phase 4» the WhatsApp client has named since INI-014, now shipped with
its go-ahead. The rules under test are the ones that keep an automatic mouth safe:

  · NEVER a group — an auto-reply in a group answers people who were not talking to him;
  · email only when the mail is ADDRESSED to him — a vacation reply to every newsletter is spam;
  · once per chat per 24 h, against a DURABLE ledger (V2-607: an in-memory guard cannot dedupe against a
    durable source — the reply must stay suppressed across an engine restart);
  · the hours window bounds WHEN it speaks, wrap-around included, and a malformed window degrades to
    «always» — never to surprise windows the operator did not set.

The owner half runs the REAL `_Owner._auto_reply` against the real store, with only the bus publisher
captured — the decision, the ledger write and the publish are the product path, not a mirror of it.
"""
from __future__ import annotations

import time

import pytest

from widgets import store as wstore
from widgets.mensajeria import autorespond, data


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    yield


def _enable(platform="whatsapp", text="De vacaciones hasta el lunes", hours=None):
    db = data.load_db()
    autorespond.set_config(db, platform, text=text, hours=hours)
    wstore.save("mensajeria", db)


def _owner_auto(platform, items):
    from widgets.mensajeria import owner
    return owner._OWNER._auto_reply(platform, items)


# ── the decision module ──────────────────────────────────────────────────────

def test_hours_window_wraps_midnight():
    assert autorespond.within_hours("22:00-08:00", (23, 30)) is True
    assert autorespond.within_hours("22:00-08:00", (7, 59)) is True
    assert autorespond.within_hours("22:00-08:00", (12, 0)) is False
    assert autorespond.within_hours("09:00-17:00", (12, 0)) is True
    assert autorespond.within_hours("garbage", (12, 0)) is True, \
        "a malformed window must degrade to ALWAYS for an enabled responder, never to surprise windows"


def test_enabling_without_text_is_not_enabled():
    db = {}
    autorespond.set_config(db, "whatsapp", enabled=True)
    assert autorespond.config_for(db, "whatsapp")["enabled"] is False


# ── the owner path, end to end ───────────────────────────────────────────────

def test_a_direct_chat_gets_one_reply_and_the_cooldown_is_durable(monkeypatch):
    _enable()
    from connectors.messaging import ingest
    sent = []
    monkeypatch.setattr(ingest, "publish_reply", lambda r: sent.append(dict(r)))
    item = {"platform": "whatsapp", "chatId": "111", "senderId": "111", "messageId": "w1", "isGroup": False}
    assert _owner_auto("whatsapp", [item]) == 1
    assert sent[0]["text"] == "De vacaciones hasta el lunes" and sent[0]["to"] == "111"
    # Second message from the same chat, same day: the ledger — reloaded FRESH from disk, as a restart
    # would — suppresses it.
    assert _owner_auto("whatsapp", [dict(item, messageId="w2")]) == 0
    assert len(sent) == 1
    ledger = data.load_db().get("auto_replied") or {}
    assert "whatsapp|111" in ledger, "the ledger must be durable, not process memory"


def test_a_group_never_gets_an_auto_reply(monkeypatch):
    _enable()
    from connectors.messaging import ingest
    sent = []
    monkeypatch.setattr(ingest, "publish_reply", lambda r: sent.append(r))
    assert _owner_auto("whatsapp", [{"platform": "whatsapp", "chatId": "g1", "messageId": "w3",
                                     "isGroup": True}]) == 0
    assert sent == []


def test_email_only_replies_to_mail_addressed_to_him(monkeypatch):
    _enable("email", "Fuera de la oficina")
    from connectors.messaging import ingest
    sent = []
    monkeypatch.setattr(ingest, "publish_reply", lambda r: sent.append(dict(r)))
    newsletter = {"platform": "email", "chatId": "news@list.com", "messageId": "9", "isGroup": False,
                  "dirigido_a_mi": False}
    direct = {"platform": "email", "chatId": "amigo@x.com", "messageId": "10", "isGroup": False,
              "dirigido_a_mi": True, "subject": "consulta", "msgid": "<m1>"}
    assert _owner_auto("email", [newsletter, direct]) == 1
    assert sent[0]["to"] == "amigo@x.com" and sent[0]["msgid"] == "<m1>", \
        "the reply must carry the threading identity so it lands on the mail it answers"


def test_disabled_or_cleared_sends_nothing(monkeypatch):
    from connectors.messaging import ingest
    sent = []
    monkeypatch.setattr(ingest, "publish_reply", lambda r: sent.append(r))
    item = {"platform": "whatsapp", "chatId": "111", "messageId": "w1", "isGroup": False}
    assert _owner_auto("whatsapp", [item]) == 0          # never configured
    _enable()
    data.apply_action("clear_autoresponder", {"platform": "whatsapp"})
    assert _owner_auto("whatsapp", [item]) == 0          # configured then cleared
    assert sent == []


def test_the_original_message_stays_pending(monkeypatch):
    """An automatic «estoy fuera» does not DEAL with the message: nothing may mark it read or remove it —
    the operator still has to see it when he returns."""
    _enable()
    from connectors.messaging import ingest
    monkeypatch.setattr(ingest, "publish_reply", lambda r: None)
    db = data.load_db()
    db["items"] = [{"platform": "whatsapp", "chatId": "111", "messageId": "w1", "from": "Jose",
                    "body": "hola", "urgencia": "media", "dirigido_a_mi": True}]
    wstore.save("mensajeria", db)
    _owner_auto("whatsapp", [dict(db["items"][0], isGroup=False)])
    after = data.load_db()
    assert len(after.get("items") or []) == 1, "the pending item must survive the auto-reply"
    assert not (after.get("pending_read") or []), "no mark-read may be queued for it"
