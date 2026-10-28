"""Telegram conversations are walked back to their beginning ONCE, into the archive (connectors/telegram/backfill.py).

Same policy as WhatsApp (connectors/messaging/history.py): text only, people and groups but never broadcast
channels, one page per tick and on its own task so a flood wait cannot hold up the live loop. Telegram pages
exactly, so a page shorter than asked is the beginning of the conversation.
"""
from __future__ import annotations

import asyncio
import datetime as dt
from types import SimpleNamespace

import pytest

from connectors.messaging import archive


@pytest.fixture
def tg(tmp_path, monkeypatch):
    from widgets import store as wstore
    from connectors.telegram import backfill
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    archive.reset()
    monkeypatch.setattr(backfill, "GAP_S", 0)
    yield backfill
    archive.reset()


def _dialog(i, *, channel=False, group=False):
    return SimpleNamespace(id=i, name=f"chat {i}", is_channel=channel or group, is_group=group, entity=i)


def _msg(i):
    return SimpleNamespace(id=i, message=f"m{i}", out=False, media=None, photo=None, document=None, voice=None,
                           video=None, video_note=None, audio=None,
                           date=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=i),
                           get_sender=None)


class _Client:
    def __init__(self, history):
        self.history, self.asked = history, []

    async def iter_dialogs(self, limit):
        for d in (_dialog(1), _dialog(2, channel=True), _dialog(3, group=True)):
            yield d

    async def get_messages(self, entity, limit, offset_id):
        self.asked.append((entity, offset_id))
        older = [m for m in self.history.get(entity, []) if not offset_id or m < offset_id]
        return [_msg(m) for m in sorted(older, reverse=True)[:limit]]


def _run(backfill, client, ticks):
    async def go():
        w = backfill.Walker()
        for _ in range(ticks):
            await w.tick(client)
            if w.task:
                await w.task
        return w
    return asyncio.run(go())


def test_people_and_groups_are_walked_to_their_beginning_and_channels_never(tg, monkeypatch):
    from connectors.telegram import service
    monkeypatch.setattr(tg, "PAGE", 2)

    async def entry(m, chat_id):
        return {"messageId": f"{chat_id}:{m.id}", "dir": "in", "from": "x", "body": m.message,
                "ts": m.date.timestamp()}
    monkeypatch.setattr(service, "_history_entry", entry)
    client = _Client({1: [10, 11, 12], 3: [5]})
    _run(tg, client, ticks=6)
    assert archive.count("telegram", "1") == 3 and archive.count("telegram", "3") == 1
    assert archive.backfill_state("telegram", "1")["done"] == 1 and archive.backfill_state("telegram", "3")["done"] == 1
    assert 2 not in [e for e, _ in client.asked], "a broadcast channel is a feed, never walked"
    assert (1, 0) in client.asked and (1, 11) in client.asked, "the next page starts from the oldest held"


def test_the_walk_can_be_switched_off(tg, monkeypatch):
    monkeypatch.setenv("TG_BACKFILL", "0")
    client = _Client({1: [1]})
    _run(tg, client, ticks=2)
    assert client.asked == []


def test_the_telegram_session_is_named_zaelar():
    """The operator's «Active sessions» list names this session; it is Zaelar, not the library's default."""
    src = open("connectors/telegram/service/__init__.py", encoding="utf-8").read()
    assert 'device_model="Zaelar Agent"' in src and 'system_version="Zaelar"' in src
