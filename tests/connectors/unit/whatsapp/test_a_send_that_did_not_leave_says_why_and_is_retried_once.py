"""A transport failure is not «that number may not have WhatsApp» (V2-854 F4, I4).

Measured on his engine (2026-11-05 15:46): the bridge's socket dropped mid-send (`Connection Closed` 428, a 408
close), the request timed out with an EMPTY exception, and the line told him a cause nothing had measured; WhatsApp
reconnected twelve seconds later and nothing retried. Here, with a faked bridge:

  · the failure carries its OWN cause — the bridge's sentence, or the exception's class when it has none — and never
    a guess about the number;
  · a LINK failure (no answer, «not connected», or the bridge not connected right after its error) is held and sent
    ONCE on the next reconnect, after the record had time to settle; the echo of that retry says `retried` and the
    card's failed row becomes sent;
  · before that second try the card's own sent record decides: a message already in that conversation is never sent
    twice; a refusal is never retried; a retry that fails again is not held again; a hold past its window is said.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from connectors.messaging import ingest
from connectors.whatsapp import client
from connectors.whatsapp import service as wa
from connectors.whatsapp.service import outbound
from widgets.mensajeria import sent

LID = "112233445566@lid"
ORDER = {"ref": "s-9", "platform": "whatsapp", "to": "+34 600 000 020", "chatId": LID, "name": "Olga Ferrer",
         "contactId": "c20", "text": "¿A qué hora llegas?"}


class _Inbox:
    def __init__(self, *orders):
        self._orders = list(orders)

    def drain(self):
        out, self._orders = self._orders, []
        return out


@pytest.fixture
def bridge(monkeypatch):
    st = {"events": [], "notes": [], "sent": [], "fail": [], "health": "connected", "record": []}
    monkeypatch.setattr(ingest, "v2_enabled", lambda: True)
    monkeypatch.setattr(ingest.bus, "emit_sync", lambda topic, payload=None: st["events"].append((topic, dict(payload or {}))))
    monkeypatch.setattr(wa, "_note", lambda t: st["notes"].append(t))
    monkeypatch.setattr(wa, "_held", [])

    async def _send(chat_id, text, reply_to=None):
        if st["fail"]:
            raise st["fail"].pop(0)
        st["sent"].append(chat_id)
        return {"messageId": f"wa-{len(st['sent'])}"}

    async def _health():
        return {"status": st["health"]}
    monkeypatch.setattr(client, "send_message", _send)
    monkeypatch.setattr(client, "health", _health)
    monkeypatch.setattr(outbound.store, "load", lambda: {"threads": {
        f"whatsapp|{LID}": {"name": "Olga Ferrer", "msgs": list(st["record"])}}})
    st["of"] = lambda topic: [p for t, p in st["events"] if t == topic]
    return st


def _drain(order=None):
    wa._send_inbox = _Inbox(dict(order or ORDER))
    asyncio.run(wa._drain_sends())


@pytest.mark.parametrize("lang, guess", [("en", "may not have"), ("es", "no tenga")])
def test_an_empty_timeout_says_its_real_cause_and_is_held(bridge, monkeypatch, lang, guess):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    bridge["fail"] = [asyncio.TimeoutError()]
    _drain()
    failed = bridge["of"](ingest.TOPIC_SEND_FAILED)
    assert failed and failed[0]["reason"] == "TimeoutError", failed
    assert len(bridge["notes"]) == 1 and "TimeoutError" in bridge["notes"][0] and "Olga" in bridge["notes"][0]
    assert guess not in bridge["notes"][0], "a cause nothing measured"
    assert [h["chatId"] for h in wa._held] == [LID]


def test_not_connected_is_a_link_failure_and_is_held(bridge):
    bridge["fail"] = [client.BridgeError("POST /send → 503", status=503, error="Not connected to WhatsApp")]
    _drain()
    assert bridge["of"](ingest.TOPIC_SEND_FAILED)[0]["reason"] == "Not connected to WhatsApp"
    assert len(wa._held) == 1


def test_a_refusal_with_the_link_up_carries_the_bridges_sentence_and_is_never_retried(bridge):
    bridge["fail"] = [client.BridgeError("POST /send → 500", status=500, error="jid not found")]
    _drain()
    assert "jid not found" in bridge["notes"][0] and not wa._held


def test_an_error_while_the_link_drops_is_the_links(bridge):
    bridge["fail"] = [client.BridgeError("POST /send → 500", status=500, error="Connection Closed")]
    bridge["health"] = "disconnected"
    _drain()
    assert len(wa._held) == 1


def _reconnect_and_retry(at_offset: float = -60.0):
    for h in wa._held:
        h["at"] = time.time() + at_offset
    asyncio.run(outbound.retry_held(time.time() - outbound.SETTLE_S - 1))


def test_the_held_send_goes_once_on_the_next_reconnect_and_its_echo_says_retried(bridge):
    bridge["fail"] = [asyncio.TimeoutError()]
    _drain()
    asyncio.run(outbound.retry_held(0.0))                  # still down: nothing is sent
    asyncio.run(outbound.retry_held(time.time()))           # reconnected a moment ago: the record is still settling
    assert bridge["sent"] == [] and len(wa._held) == 1
    _reconnect_and_retry()
    assert bridge["sent"] == [LID], "the held send did not go to her chat id once"
    out = bridge["of"](ingest.TOPIC_MSG_OUT)
    assert out and out[-1]["ref"] == "s-9" and out[-1].get("retried") is True
    assert not wa._held
    _reconnect_and_retry()
    assert bridge["sent"] == [LID], "a second reconnect sent it again"


def test_a_message_the_record_shows_left_is_never_sent_twice(bridge):
    bridge["fail"] = [asyncio.TimeoutError()]
    _drain()
    bridge["record"].append({"id": "wa-x", "dir": "out", "body": ORDER["text"], "ts": time.time()})
    _reconnect_and_retry(at_offset=-30.0)
    assert bridge["sent"] == [] and not wa._held
    assert len(bridge["notes"]) == 2, "he is not told it did go out"


def test_a_retry_that_fails_again_is_not_held_again(bridge):
    bridge["fail"] = [asyncio.TimeoutError(), asyncio.TimeoutError()]
    _drain()
    _reconnect_and_retry()
    assert not wa._held and bridge["sent"] == []
    assert len(bridge["of"](ingest.TOPIC_SEND_FAILED)) == 2


def test_a_hold_past_its_window_is_dropped_and_said(bridge):
    bridge["fail"] = [asyncio.TimeoutError()]
    _drain()
    _reconnect_and_retry(at_offset=-outbound.RETRY_WITHIN_S - 5)
    assert bridge["sent"] == [] and not wa._held and len(bridge["notes"]) == 2


def test_the_cards_failed_row_becomes_sent_only_on_the_retrys_echo():
    db: dict = {}
    sent.outbox_queue(db, "s-9", "whatsapp", LID, "k", "hola")
    assert sent.outbox_settle(db, "s-9", False, "TimeoutError")
    assert not sent.outbox_settle(db, "s-9", True), "a late echo turned a failure into a success"
    assert sent.outbox_settle(db, "s-9", True, retried=True)
    assert db["outbox"][0]["state"] == "sent"
