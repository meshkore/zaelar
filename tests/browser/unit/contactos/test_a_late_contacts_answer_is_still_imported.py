"""An address book that arrives after its ask gave up is still imported (2026-09-26).

Measured on the operator's engine: Telegram answered the contacts ask in 24 s and 27 s (the address book plus
the members of 56 groups) against a 25 s wait. The subscription was closed before the answer landed, so the
import never happened — every time — and «trae mis contactos de Telegram» brought nothing, while the log said
«Telegram contactos → 1848 personas». Now the ask keeps listening for a while, and the contacts cron absorbs
whatever came back late.
"""

from connectors.messaging import contacts_bus, ingest


def test_a_timed_out_ask_hands_its_late_answer_over(monkeypatch):
    monkeypatch.setattr(contacts_bus, "_late", {})
    got = contacts_bus.request("telegram", timeout=0.3)
    assert got["ok"] is False and got.get("pending"), got
    assert contacts_bus.take_late("telegram") is None, "nothing has arrived yet"

    ingest.publish_contacts("telegram", [{"name": "cryptonite", "channels": [{"platform": "telegram",
                                                                             "chatId": "42"}]}], [])
    from tests.waiting import until_sync     # the bus may deliver on the next tick
    late = until_sync(lambda: contacts_bus.take_late("telegram"), "the late contacts answer to reach the bus",
                      timeout_s=2.0, poll_s=0.05)
    assert late and late["ok"] and late["contacts"][0]["name"] == "cryptonite", late
    assert contacts_bus.take_late("telegram") is None, "handed over once, then the listener is gone"


def test_a_late_listener_past_its_deadline_is_dropped(monkeypatch):
    monkeypatch.setattr(contacts_bus, "_late", {})
    monkeypatch.setattr(contacts_bus, "_LATE_S", 0.0)
    contacts_bus.request("whatsapp", timeout=0.1)
    assert contacts_bus.take_late("whatsapp") is None
    assert "whatsapp" not in contacts_bus._late
