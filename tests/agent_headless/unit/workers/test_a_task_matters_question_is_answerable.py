"""A task matter's question is a durable ask he can answer (V2-857 P0-2, architecture audit 2026-11-05).

`task_event.told(ask=True)` — a party's proposal on a negotiation errand, a question a stream wakes with — made the row
wait for his answer with NO question id: neither the screen nor the brief's binding verdict could answer it, so it
sat until the 7-day expiry cancelled it. It goes through the one asker now, with its `ask_id`; his answer ends the wait.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture
def row(monkeypatch):
    from nucleo.circuit import asker, ledger
    from nucleo.events import task_event
    asked, waits, resumed = [], [], []
    monkeypatch.setattr(ledger, "store", lambda: SimpleNamespace(task_get=lambda uid: {"id": uid}))
    monkeypatch.setattr(ledger, "waiting", lambda *a, **k: waits.append(a))
    monkeypatch.setattr(ledger, "resumed", lambda uid: resumed.append(uid))
    monkeypatch.setattr(asker, "ask", lambda uid, entry, bus_id="": asked.append((uid, entry)) or entry["ask_id"])
    monkeypatch.setattr(task_event, "_soon", lambda coro: coro.close())
    return SimpleNamespace(told=task_event.told, asked=asked, waits=waits, resumed=resumed)


@pytest.mark.parametrize("line", ["Quinn propone una cita el jueves a las 10. Espera tu sí.",
                                  "Quinn proposes Thursday at 10. It waits for your yes."])
def test_a_question_on_a_row_carries_its_ask_id(row, line):
    row.told(line, task_id="e-1", ask=True)
    (uid, entry), = row.asked
    assert uid == "e-1" and entry["ask_id"].startswith("e-1-m") and entry["said"] is True
    assert not row.waits, "no wait without its question"


def test_his_answer_ends_the_wait(row):
    import asyncio
    from nucleo.request import inline_ask
    inline_ask._TAKEN.clear()
    row.told("Quinn proposes Thursday at 10.", task_id="e-2", ask=True)
    _uid, entry = row.asked[0]
    assert asyncio.run(inline_ask.rerun("e-2", entry, "yes, accept it"))["answered"] is True
    assert row.resumed == ["e-2"]


def test_a_wait_for_something_else_is_not_a_question(row):
    row.told("Waiting for Quinn's reply.", task_id="e-3", waiting_for="party_reply")
    assert not row.asked and row.waits
