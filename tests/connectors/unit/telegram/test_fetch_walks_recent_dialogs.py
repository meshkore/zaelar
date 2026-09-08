"""V2-624 — the Telegram half of «chupar más mensajes»: the account enumerates its OWN dialogs, so
«conversations with movement in the last N hours» is an exact query here. What the walk must honour:

  · dialogs come newest-first, so the FIRST stale one ends the walk (a busy account is not scanned whole);
  · a broadcast channel is a feed, not a conversation — excluded;
  · each published batch carries the dialog's NAME and its group flag, so a thread born from the pull is
    labeled correctly instead of after whichever member spoke first;
  · messages older than the cutoff inside a live dialog are trimmed.
"""
from __future__ import annotations

import asyncio
import datetime as dt

import pytest

pytest.importorskip("telethon")

from connectors.messaging import ingest
from connectors.telegram import service


def _when(hours_ago: float) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_ago)


class _Msg:
    def __init__(self, mid, hours_ago, body, out=False):
        self.id = mid
        self.date = _when(hours_ago)
        self.message = body
        self.out = out
        self.photo = self.voice = self.video = self.video_note = None
        self.audio = self.document = self.media = None

    async def get_sender(self):
        raise RuntimeError("no sender in the fake")


class _Dialog:
    def __init__(self, did, name, hours_ago, is_group=False, is_channel=False):
        self.id = did
        self.name = name
        self.date = _when(hours_ago)
        self.is_group = is_group
        self.is_channel = is_channel
        self.entity = did


class _Client:
    def __init__(self, dialogs, msgs_by_entity):
        self._dialogs = dialogs
        self._msgs = msgs_by_entity
        self.walked = []

    async def iter_dialogs(self, limit=60):
        for d in self._dialogs:
            yield d

    async def get_messages(self, entity, limit=20):
        self.walked.append(entity)
        return list(self._msgs.get(entity, []))


class _FakeInbox:
    def __init__(self, orders):
        self._orders = list(orders)

    def drain(self):
        out, self._orders = self._orders, []
        return out


@pytest.fixture(autouse=True)
def _quiet_notes(monkeypatch):
    monkeypatch.setattr(service, "_note", lambda *a, **k: None)
    yield


def test_the_walk_skips_stale_dialogs_and_survives_a_pinned_one_at_the_head(monkeypatch):
    client = _Client(
        dialogs=[
            _Dialog(9, "Anclado Viejo", 400.0),                           # PINNED and idle: heads the list
            _Dialog(1, "Marta", 1.0),
            _Dialog(2, "Canal Noticias", 2.0, is_channel=True),          # broadcast: excluded
            _Dialog(3, "Grupo Viaje", 3.0, is_group=True, is_channel=True),  # megagroup: included
            _Dialog(4, "Viejo", 100.0),                                   # stale mid-list: skipped, not fatal
        ],
        msgs_by_entity={
            1: [_Msg(11, 0.5, "reunión mañana"), _Msg(10, 90.0, "antiguo, fuera de ventana")],
            3: [_Msg(31, 2.5, "vuelos el 12")],
        },
    )
    monkeypatch.setattr(service, "_client", client)
    monkeypatch.setattr(service, "_fetch_inbox", _FakeInbox([{"since_hours": 72}]))
    published = []
    monkeypatch.setattr(ingest, "publish_history",
                        lambda platform, chat_id, msgs, complete=False, error="", name="", is_group=None:
                        published.append({"chat": chat_id, "msgs": msgs, "name": name, "group": is_group}))
    asyncio.run(service._drain_fetch())

    by_chat = {p["chat"]: p for p in published}
    assert set(by_chat) == {1, 3}, by_chat
    assert 9 not in client.walked and 4 not in client.walked, \
        "stale dialogs are skipped without fetching their messages"
    assert by_chat[1]["name"] == "Marta" and by_chat[1]["group"] is False
    assert by_chat[3]["name"] == "Grupo Viaje" and by_chat[3]["group"] is True
    assert len(by_chat[1]["msgs"]) == 1, "the 90-hour-old message inside a live dialog must be trimmed"
    assert by_chat[1]["msgs"][0]["body"] == "reunión mañana"
    assert by_chat[1]["msgs"][0]["read"] is True
