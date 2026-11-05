"""V2-852 T09 · A question reaches him once, and never after he answered it (invariant I4).

Measured in his session of 2026-11-05: a browser task's question was painted, its say timed out («SIN CONFIRMAR»),
he answered by text — and the question was still heard and shown again minutes later. A notice's identity for a
QUESTION is its `ask_id` (`ask:<ask_id>`), whatever door words it and however it is worded; and an owed question whose
ask is no longer open is closed `answered` — never pushed to a phone nor painted on the next screen.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import runstate
from nucleo.pulse import notices


@pytest.fixture
def ledger(monkeypatch):
    from voice import proactive
    said, pushed = [], []

    async def voice(title, text, **kw):
        said.append(text)
        return False                    # the say did not confirm (the measured «SIN CONFIRMAR»)
    monkeypatch.setattr(proactive, "notify", voice)
    monkeypatch.setattr(notices, "push", lambda row: pushed.append(row["dedupe_key"]) or 0)
    monkeypatch.setattr(notices, "_targets", lambda: ["phone"])
    monkeypatch.setattr(notices, "someone_looking", lambda now=None: False)
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    return said, pushed


def _open_asks(monkeypatch, ids):
    from nucleo.cli import worker_api_asks
    monkeypatch.setattr(worker_api_asks, "pending_asks", lambda: [{"ask_id": i, "corr_id": i} for i in ids])


def test_one_question_worded_by_two_doors_is_one_notice(ledger, monkeypatch):
    said, _ = ledger
    first = asyncio.run(notices.notify("zaelar", "The flat search asks: which district, Gràcia or Sants?",
                                       task_id="r1", ask_id="a-flat-1"))
    again = asyncio.run(notices.notify("navegador", "Task r1 needs an answer: Gràcia or Sants?",
                                       task_id="r1", ask_id="a-flat-1"))
    assert again["duplicate"] is True and again["id"] == first["id"]
    assert len(said) == 1, f"the same question went to the voice {len(said)} times"
    other = asyncio.run(notices.notify("zaelar", "Which day suits you for the flight?", task_id="r1", ask_id="a-2"))
    assert other["duplicate"] is False, "a NEW question of the same task is its own notice"


def test_an_owed_question_he_answered_is_never_delivered_later(ledger, monkeypatch):
    _, pushed = ledger
    _open_asks(monkeypatch, ["a-flight-7"])
    row = asyncio.run(notices.notify("zaelar", "Shall I book the 9:40 flight?", task_id="r7", ask_id="a-flight-7"))
    assert row["state"] == "owed"
    _open_asks(monkeypatch, [])                                  # he answered it by text
    notices._last_retry[0] = 0.0
    import time
    notices._store.update(row["id"], next_try_at=int(time.time()) - 1)
    before = len(pushed)
    assert asyncio.run(notices.retry_owed()) == 0 and len(pushed) == before, "an answered question was pushed"
    assert notices.drain_to_screen("desktop:x") == 0, "an answered question was painted on the next screen"
    assert notices.get(row["id"])["state"] == "answered"


def test_an_owed_question_still_open_is_still_delivered(ledger, monkeypatch):
    _, pushed = ledger
    _open_asks(monkeypatch, ["a-open"])
    row = asyncio.run(notices.notify("zaelar", "Which colour do you prefer?", task_id="r8", ask_id="a-open"))
    assert row["state"] == "owed"
    assert notices.drain_to_screen("desktop:x") == 1 and notices.get(row["id"])["state"] == "shown"


def test_the_pulse_relays_a_question_with_its_ask_identity(monkeypatch):
    import time
    from nucleo.pulse import loop as _loop
    from nucleo import dispatch
    from nucleo.cli import worker_api
    seen = []

    async def deliver(title, text, **kw):
        seen.append(kw)
    monkeypatch.setattr(dispatch, "active_sessions", lambda: [])
    monkeypatch.setattr(dispatch, "sync_state", lambda: None)
    monkeypatch.setattr(worker_api, "pending_asks", lambda: [{"corr_id": "q9", "ask_id": "q9", "task_id": "r9",
                                                             "question": "Gràcia or Sants?", "said": False}])
    lp = _loop.OrchestratorLoop(deliver=deliver)
    lp._last_reconcile = time.time()
    lp._reshown = True
    asyncio.run(lp._supervise_workers(time.time()))
    assert seen and seen[0].get("ask_id") == "q9", seen
    assert notices.identity("any wording", key="ask:q9", ask_id="q9") == "ask:q9"
