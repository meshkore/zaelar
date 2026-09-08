"""V2-624 — the email half of «chupar más mensajes»: a platform-wide pull serves «the conversations with
activity in the window». IMAP's SINCE is DAY-granular, so the search over-fetches to the start of the cutoff
day and the SERVICE trims by each message's own timestamp — the trim is the half a unit test can pin. What
arrives is grouped by sender (the email chatId), labeled, and published as READ scrollback through the same
connector.history seam «load previous» uses — never into triage.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from connectors.email import service
from connectors.messaging import ingest


class _FakeMailbox:
    def __init__(self, msgs):
        self._msgs = msgs
        self.asked = None

    def search_since(self, hours, limit=100, media_dir=None):
        self.asked = (hours, limit)
        return list(self._msgs)


class _FakeInbox:
    def __init__(self, orders):
        self._orders = list(orders)

    def drain(self):
        out, self._orders = self._orders, []
        return out


@pytest.fixture(autouse=True)
def _quiet_notes(monkeypatch):
    import voice.brain_notes as bn
    monkeypatch.setattr(bn, "push", lambda *a, **k: None)
    yield


def _mail(uid, sender, name, subject, body, ts):
    return {"messageId": uid, "chatId": sender, "senderId": sender, "senderName": name,
            "subject": subject, "body": body, "timestamp": ts, "isGroup": False}


def test_the_pull_groups_by_sender_labels_and_trims_to_the_hour(monkeypatch):
    now = time.time()
    mb = _FakeMailbox([
        _mail("1", "ana@x.com", "Ana", "vuelos", "salen el 12", now - 3600),
        _mail("2", "ana@x.com", "Ana", "hoteles", "he visto dos", now - 1800),
        _mail("3", "luis@y.com", "Luis", "riad", "reservado", now - 7200),
        # Same cutoff DAY but outside the requested hours: SINCE over-fetched it; the service must trim it.
        _mail("4", "old@z.com", "Old", "viejo", "fuera de ventana", now - 80 * 3600),
    ])
    published = []
    monkeypatch.setattr(ingest, "publish_history",
                        lambda platform, chat_id, msgs, complete=False, error="", name="", is_group=None:
                        published.append({"chat": chat_id, "msgs": msgs, "name": name, "group": is_group}))
    monkeypatch.setattr(service, "_fetch_inbox", _FakeInbox([{"since_hours": 72}]))
    asyncio.run(service._drain_fetch(mb))

    assert mb.asked[0] == 72.0
    by_chat = {p["chat"]: p for p in published}
    assert set(by_chat) == {"ana@x.com", "luis@y.com"}, "the stale sender must be trimmed, not published"
    ana = by_chat["ana@x.com"]
    assert ana["name"] == "Ana" and ana["group"] is False and len(ana["msgs"]) == 2
    row = ana["msgs"][0]
    assert row["read"] is True, "pulled activity is scrollback, never something demanding attention"
    assert row["body"].startswith("vuelos\n"), "the subject rides as the first line, the widget's title split"


def test_an_empty_window_publishes_nothing(monkeypatch):
    published = []
    monkeypatch.setattr(ingest, "publish_history", lambda *a, **k: published.append(a))
    monkeypatch.setattr(service, "_fetch_inbox", _FakeInbox([{"since_hours": 24}]))
    asyncio.run(service._drain_fetch(_FakeMailbox([])))
    assert published == []
