"""The send uses the channel the contact really has (V2-854 F4): her WhatsApp chat id before a raw phone.

Measured on his engine (2026-11-05 17:22): the message reached the person he meant through her `@lid` chat id, the
id WhatsApp itself keys her conversation by — a number turned into `<digits>@s.whatsapp.net` is a different
conversation (or none) for a contact WhatsApp addresses by `@lid`. Verified, not changed: the send door's target
carries the stored channel's `chatId`, and the connector addresses the chat id before it ever builds one from a phone.
A contact with only a phone still goes by that phone, because he named WhatsApp.
"""
from __future__ import annotations

import asyncio

import pytest

from connectors.messaging import ingest

LID = "998877665544@lid"
PEOPLE = [
    {"id": "c10", "kind": "person", "name": "Nerea Solís Prat", "phone": "+34 600 000 010",
     "channels": [{"platform": "whatsapp", "handle": "+34 600 000 010", "chatId": LID, "source": "observed",
                   "last_seen": 1.0, "volume": 3}]},
    {"id": "c11", "kind": "person", "name": "Bruno Esteve Lluch", "phone": "+34 600 000 011"},
]


@pytest.fixture
def directory(monkeypatch):
    monkeypatch.setattr("widgets.directory._contacts", lambda: [dict(c) for c in PEOPLE])


class _Inbox:
    def __init__(self, *orders):
        self._orders = list(orders)

    def drain(self):
        out, self._orders = self._orders, []
        return out


def _target(who):
    from widgets.mensajeria.outbound import targets
    return targets.resolve_target({"contact": who, "channel": "whatsapp", "text": "¿cuándo vuelves?"})


@pytest.mark.parametrize("who", ["Nerea Solís Prat", "Nerea"])
def test_the_target_carries_her_chat_id_before_her_phone(directory, who):
    t = _target(who)
    assert t["ok"] and t["platform"] == "whatsapp" and t["chatId"] == LID, t


def test_the_connector_addresses_the_chat_id_and_never_rebuilds_one_from_the_phone(directory, monkeypatch):
    from connectors.whatsapp import service as wa
    sent = []

    async def _send(chat_id, text, reply_to=None):
        sent.append(chat_id)
        return {"messageId": "wa-1"}

    t = _target("Nerea")
    monkeypatch.setattr(ingest, "v2_enabled", lambda: True)
    monkeypatch.setattr(ingest.bus, "emit_sync", lambda topic, payload=None: None)
    monkeypatch.setattr(wa, "_send_inbox", _Inbox({"ref": "s-lid", "platform": "whatsapp", "to": t["to"],
                                                   "chatId": t["chatId"], "name": t["name"], "text": "hola"}))
    monkeypatch.setattr(wa.client, "send_message", _send)
    asyncio.run(wa._drain_sends())
    assert sent == [LID], sent


def test_a_contact_with_only_a_phone_goes_by_that_phone(directory):
    t = _target("Bruno")
    assert t["ok"] and t["chatId"] == "" and t["to"] == "+34 600 000 011", t
    from connectors.whatsapp.service import outbound
    assert outbound._jid(t["to"]) == "34600000011@s.whatsapp.net"
