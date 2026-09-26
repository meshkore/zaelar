"""An address book that arrives after its ask gave up is still imported (2026-09-26).

Measured on the operator's engine: Telegram answered the contacts ask in 24 s and 27 s (the address book plus
the members of 56 groups) against a 25 s wait. The subscription was closed before the answer landed, so the
import never happened — every time — and «trae mis contactos de Telegram» brought nothing, while the log said
«Telegram contactos → 1848 personas». Now the ask keeps listening for a while, and the contacts cron absorbs
whatever came back late.
"""
import time

from connectors.messaging import contacts_bus, ingest


def test_a_timed_out_ask_hands_its_late_answer_over(monkeypatch):
    monkeypatch.setattr(contacts_bus, "_late", {})
    got = contacts_bus.request("telegram", timeout=0.3)
    assert got["ok"] is False and got.get("pending"), got
    assert contacts_bus.take_late("telegram") is None, "nothing has arrived yet"

    ingest.publish_contacts("telegram", [{"name": "cryptonite", "channels": [{"platform": "telegram",
                                                                             "chatId": "42"}]}], [])
    late = None
    for _ in range(20):                      # the bus may deliver on the next tick
        late = contacts_bus.take_late("telegram")
        if late is not None:
            break
        time.sleep(0.05)
    assert late and late["ok"] and late["contacts"][0]["name"] == "cryptonite", late
    assert contacts_bus.take_late("telegram") is None, "handed over once, then the listener is gone"


def test_a_late_listener_past_its_deadline_is_dropped(monkeypatch):
    monkeypatch.setattr(contacts_bus, "_late", {})
    monkeypatch.setattr(contacts_bus, "_LATE_S", 0.0)
    contacts_bus.request("whatsapp", timeout=0.1)
    assert contacts_bus.take_late("whatsapp") is None
    assert "whatsapp" not in contacts_bus._late


def test_the_contacts_cron_absorbs_a_late_answer(monkeypatch):
    from widgets.contactos import sources
    payload = {"ok": True, "contacts": [{"name": "cryptonite"}], "groups": []}
    monkeypatch.setattr(contacts_bus, "take_late", lambda p: payload if p == "telegram" else None)
    seen = []
    monkeypatch.setattr(sources, "_absorb", lambda s, g: seen.append((s, g)) or {"ok": True, "added": 1})
    monkeypatch.setattr(sources, "state", lambda db: {})
    import widgets.contactos.data as _d
    monkeypatch.setattr(_d, "load_db", lambda: {})
    sources.tick(None)
    assert seen == [("telegram", payload)], "the late answer must be folded into the directory"
