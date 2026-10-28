"""A data-op whose verdict cannot be READ claims nothing: never «I couldn't get that done» over an op the card did not
refuse (node 2.922).

Live, 2026-10-28 17:48 (T23): «check the chat» → the messaging lens returned his chats, the turn answered with them,
and the mouth appended «I couldn't get that done.» — `of_ops` turned an exception while reading the op's result into
an `unmet` outcome with no object and no reason. The only «unmet» is the one the card reports (`ok: False` or an
error); a task that raised, or a result the reader cannot parse, is `started` and logged.

Disarm: with the except branch appending `unmet` again, the first test goes red.
"""
from __future__ import annotations

import asyncio

from nucleo.circuit import verdict as V
from nucleo.turn import reply


def _done(result=None, exc=None):
    loop = asyncio.new_event_loop()
    try:
        f = loop.create_future()
        if exc is not None:
            f.set_exception(exc)
        else:
            f.set_result(result)
        return f
    finally:
        pass


def test_a_task_that_raised_is_started_not_unmet():
    async def run():
        f = asyncio.get_running_loop().create_future()
        f.set_exception(RuntimeError("boom"))
        return await reply.of_ops([("mensajeria", f)], timeout=0.1)
    out = asyncio.run(run())
    assert [o.verdict for o in out] == [V.STARTED.name]
    assert reply.owed(out, "You've got 19 chats") == []


def test_a_result_the_reader_cannot_parse_is_started_not_unmet(monkeypatch):
    monkeypatch.setattr(reply, "of_op", lambda card, action, res: (_ for _ in ()).throw(TypeError("odd shape")))

    async def run():
        f = asyncio.get_running_loop().create_future()
        f.set_result({"chats": 19})
        return await reply.of_ops([("mensajeria", f)], timeout=0.1)
    out = asyncio.run(run())
    assert [o.verdict for o in out] == [V.STARTED.name]


def test_a_refusal_the_card_reports_is_still_unmet():
    async def run():
        f = asyncio.get_running_loop().create_future()
        f.set_result({"ok": False, "message": "No sigo ese canal."})
        return await reply.of_ops([("youtube::open_channel", f)], timeout=0.1)
    out = asyncio.run(run())
    assert [o.verdict for o in out] == [V.UNMET.name]
