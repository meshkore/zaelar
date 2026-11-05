"""V2-852 I1 · A worker is named by its ROW from birth, and registered before its first act.

Measured in his session and the C13 replay: the results card's owner was `errand:3` (the dispatcher's boot-local
number) while the row was `abffbc-3`, because the sheet opened before the record was registered and before it had its
row id; the out-of-turn lines («I stopped…», the delivery) were keyed by that number too — after a restart a new
worker `3` would find the old line's key already spent. Now the record carries its row id and sits in the registry
when its first act (the sheet) runs, and the delivery and the stuck notice are keyed by the row.
"""
from __future__ import annotations

import asyncio

from nucleo import dispatch
from tests.agent_headless.unit.test_a_commission_leaves_a_durable_row import (  # noqa: F401 — fixtures
    _commission, _hash_backend, _no_sessions_left_behind, fresh_db)


def test_the_first_show_already_knows_the_row_and_the_registry_holds_it(fresh_db, monkeypatch):
    seen = []

    def sheet_open(rec):
        seen.append((str(rec.uid), any(r is rec for r in dispatch._SESSIONS.values())))
    monkeypatch.setattr(dispatch, "_sheet_open", sheet_open)
    monkeypatch.setattr(dispatch.surfaces, "opens_sheet", lambda s: True)
    live, _ = asyncio.run(_commission(monkeypatch, "find me three second-hand road bikes in Valencia"))
    uid = live[0]["id"]
    assert seen == [(uid, True)], f"the first show ran as {seen}, the row is {uid}"


def test_the_delivery_line_is_keyed_by_the_row(fresh_db, monkeypatch):
    from nucleo.pulse import notices
    keys = []

    async def notify(title, text, **kw):
        keys.append((kw.get("key"), kw.get("task_id")))
        return {"id": 1, "state": "spoken", "channel": "voice", "duplicate": False}
    monkeypatch.setattr(notices, "notify", notify)
    live, done = asyncio.run(_commission(monkeypatch, "find me a quiet café to work from in Lyon"))
    uid = done[0]["id"]
    assert (f"notice:{uid}", uid) in keys, keys
