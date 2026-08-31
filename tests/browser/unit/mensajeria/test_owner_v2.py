#
# test_owner_v2.py — the messaging widget's owner backend (V2-008). Verifies the v2 reshape END-TO-END at the
# bus boundary (no network, with stubbed triage): an incoming RELEVANT connector.msg is triaged, surfaces in the UI store
# and (through the same upsert) in memory; an irrelevant one does NOT surface; connector.status is reflected in the card; and
# a "read" action publishes msg.mark_read to the bus (so the correct connector marks it as read in its app).
# Run: .venv/bin/python -m pytest tests/browser/unit/mensajeria/test_owner_v2.py
#
import asyncio

import pytest

import bus
from connectors.messaging import ingest, notify
from connectors.messaging import store as msgstore
from widgets import store as wstore
from widgets.mensajeria import data, owner as owner_mod, triage_agent


@pytest.fixture
def iso(monkeypatch, tmp_path):
    """Isolates the widget store (widgets/_data → tmp), silences the memory dump and spoken notification, and
    clears the bus. Leaves the real triage_batch/handle/apply_action logic intact."""
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    wstore._last_hash.clear()
    monkeypatch.setattr(msgstore, "_to_memory", lambda items: None)

    async def _noop_announce(label, items):
        return None
    monkeypatch.setattr(notify, "announce", _noop_announce)
    bus.reset()
    yield
    bus.reset()


def _mk_owner():
    o = owner_mod._Owner()
    o._msg_sub = bus.subscribe(ingest.TOPIC_MSG)
    o._status_sub = bus.subscribe(ingest.TOPIC_STATUS)
    return o


def test_relevant_incoming_surfaces_to_store(iso, monkeypatch):
    async def fake_classify(msgs, name=None):
        return [{**m, "importante": True, "dirigido_a_mi": True, "urgencia": "alta", "motivo": "te escribe"}
                for m in msgs]
    monkeypatch.setattr(triage_agent, "classify", fake_classify)

    async def run():
        o = _mk_owner()
        ingest.publish_msg("telegram", {"messageId": "m1", "chatId": "c1", "senderId": "s1",
                                        "senderName": "Marta", "isGroup": False, "body": "¿nos vemos hoy?"})
        await o._triage_batch()

    asyncio.run(run())
    v = data.view_data()
    assert v["count"] == 1
    assert v["items"][0]["from"] == "Marta"
    assert v["items"][0]["platform"] == "telegram"


def test_irrelevant_incoming_does_not_surface(iso, monkeypatch):
    async def fake_classify(msgs, name=None):
        return [{**m, "importante": False, "dirigido_a_mi": False, "urgencia": "baja", "motivo": "spam"}
                for m in msgs]
    monkeypatch.setattr(triage_agent, "classify", fake_classify)

    async def run():
        o = _mk_owner()
        ingest.publish_msg("whatsapp", {"messageId": "x1", "chatId": "g1", "isGroup": True,
                                        "chatName": "Ofertas", "senderName": "bot", "body": "🔥 -70%"})
        await o._triage_batch()

    asyncio.run(run())
    assert data.view_data()["count"] == 0


def test_status_event_reflected_in_card(iso):
    async def run():
        o = _mk_owner()
        ingest.publish_status("telegram", "connecting", qr="data:image/png;base64,ZZZ")
        o._apply_status()

    asyncio.run(run())
    plat = data.view_data()["platforms"]["telegram"]
    assert plat["status"] == "connecting" and plat["qr"] == "data:image/png;base64,ZZZ"


def test_read_action_publishes_mark_read(iso, monkeypatch):
    async def fake_classify(msgs, name=None):
        return [{**m, "importante": True, "dirigido_a_mi": True, "urgencia": "alta", "motivo": "x"} for m in msgs]
    monkeypatch.setattr(triage_agent, "classify", fake_classify)

    marks = bus.subscribe(ingest.TOPIC_MARK_READ)

    async def run():
        o = _mk_owner()
        ingest.publish_msg("telegram", {"messageId": "m1", "chatId": "c1", "senderId": "s1",
                                        "senderName": "Ana", "isGroup": False, "body": "hola"})
        await o._triage_batch()
        assert data.view_data()["count"] == 1
        await o.handle("read", {"n": 1})

    asyncio.run(run())
    # the item was removed from the widget...
    assert data.view_data()["count"] == 0
    # ...and its key was sent to the bus so Telegram marks it as read.
    key = marks.queue.get_nowait()
    assert key["platform"] == "telegram" and key["messageId"] == "m1"
