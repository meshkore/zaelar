"""A restart must not re-announce mail that is still unread at the provider (V2-607).

MEASURED on the operator's engine, 2026-09-07, straight after V2-606 gave the widget his backlog: the same
email — uid 219719, «Pago rechazado» from Amazon.es — was announced THREE times in fourteen minutes, at
12:29:39, 12:38:21 and 12:43:17. Not a loop: one per engine restart, each on a different build. Nothing was
malfunctioning in the poller. The message is still UNREAD in Gmail, so every connect re-delivers it, correctly
and forever, while the only thing that remembered having seen it was a `set()` built in `__init__`.

That set even carried the comment «do not resurrect what the operator removed», a promise it could not keep for
the same reason: he dismisses a message, the engine restarts, IMAP still calls it unread, and it walks back in.

So the ledger is durable, lives in the store, and both questions read it: what gets STORED and what may INTERRUPT.
The restart is simulated the way it actually happens — a brand-new owner over the same store — because an
in-memory guard is precisely what a restart destroys, and a test that reuses the owner cannot see it.
"""
import asyncio

import pytest

import bus
from connectors.messaging import ingest, notify
from connectors.messaging import store as msgstore
from widgets import store as wstore
from widgets.mensajeria import data, owner as owner_mod, triage_agent


@pytest.fixture
def iso(monkeypatch, tmp_path):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    wstore._last_hash.clear()
    monkeypatch.setattr(msgstore, "_to_memory", lambda items: None)
    bus.reset()
    yield
    bus.reset()


def _mk_owner():
    """A FRESH owner — this is what a restart is. Nothing in-process survives it."""
    o = owner_mod._Owner()
    o._msg_sub = bus.subscribe(ingest.TOPIC_MSG)
    o._status_sub = bus.subscribe(ingest.TOPIC_STATUS)
    return o


def _deliver(owner, message_id):
    """One connect's delivery of the SAME unread mail — what IMAP does on every reconnect."""
    ingest.publish_msg("email", {"messageId": message_id, "chatId": "amazon", "senderName": "Amazon.es",
                                 "isGroup": False, "body": "Pago rechazado: actualiza tu información"})
    asyncio.run(owner._triage_batch())


@pytest.fixture
def urgent_triage(monkeypatch):
    async def fake_classify(msgs, name=None):
        return [{**m, "importante": True, "dirigido_a_mi": True, "urgencia": "alta", "motivo": "pago"}
                for m in msgs]
    monkeypatch.setattr(triage_agent, "classify", fake_classify)


def test_the_same_unread_mail_is_announced_once_across_restarts(iso, urgent_triage, monkeypatch):
    announced = []

    async def spy(label, items):
        announced.append([i.get("messageId") for i in items])
    monkeypatch.setattr(notify, "announce", spy)
    # He asked to be told; otherwise the default silence would hide the defect instead of proving it fixed.
    assert data.apply_action("set_notify", {"platform": "email", "notify": "all"})["ok"]

    for _ in range(3):                      # three restarts, exactly as measured
        _deliver(_mk_owner(), "219719")

    assert announced == [["219719"]], f"announced once per restart: {announced}"
    assert data.view_data()["count"] == 1, "and stored once"


def test_a_message_he_dismissed_does_not_come_back_after_a_restart(iso, urgent_triage):
    _deliver(_mk_owner(), "219719")
    assert data.view_data()["count"] == 1
    data.apply_action("dismiss", {"n": 1})
    assert data.view_data()["count"] == 0, "precondition: the dismissal took"

    _deliver(_mk_owner(), "219719")         # still unread in Gmail, so it is delivered again
    assert data.view_data()["count"] == 0, "what he removed must stay removed"


def test_the_ledger_does_not_block_a_genuinely_new_message(iso, urgent_triage):
    """The failure mode of a ledger is over-blocking. Guard it explicitly: remembering 219719 must say nothing
    about 219721, and a same-numbered id on a DIFFERENT platform is a different message."""
    _deliver(_mk_owner(), "219719")
    o = _mk_owner()
    ingest.publish_msg("email", {"messageId": "219721", "chatId": "lowi", "senderName": "Lowi",
                                 "isGroup": False, "body": "Tu factura"})
    ingest.publish_msg("telegram", {"messageId": "219719", "chatId": "c1", "senderName": "Ana",
                                    "isGroup": False, "body": "hola"})
    asyncio.run(o._triage_batch())
    ids = sorted((i["platform"], i["messageId"]) for i in data.view_data()["items"])
    assert ids == [("email", "219719"), ("email", "219721"), ("telegram", "219719")], ids


def test_the_ledger_survives_in_the_store_and_not_in_the_process(iso, urgent_triage):
    """The property itself, stated where it can fail loudly: after the delivery the record is ON DISK. A future
    refactor that moves it back into the owner passes every test above by accident on a single process."""
    _deliver(_mk_owner(), "219719")
    assert "email:219719" in msgstore.taken_ids(msgstore.load())
