"""V2-851 F2c — one answer to a waiting row runs its act ONCE, whoever triggers it (identity = the `ask_id`).

Measured (battery C3 es, «Al primero» to «which Pablo?»): the model called `send_to` naming «Pablo Ruiz» under the key
`name`; the claim read the door's slot `contact` raw, missed his answer, and the act ran on a NEW row — then the
binding verdict re-ran the retained act on the waiting row: two sends to the same person, 12 ms apart in the loopback.
"""
from __future__ import annotations

import asyncio

from memory import tasks_store as ts
from nucleo.circuit import asker
from nucleo.cli import worker_api
from nucleo.request import inline_ask

from .test_an_inline_door_question_makes_its_row_wait import _held, fresh  # noqa: F401 — the shared fixture


def test_the_slot_under_a_synonym_key_is_still_his_answer(fresh):
    """Measured (C3 es): the model named the candidate as `name`, the door's slot is `contact` — read raw, the claim
    missed, the act ran on a NEW row and the verdict re-ran the retained act: two sends to one person."""
    _held()
    assert inline_ask.claim("mensajeria", "send_to", {"name": "Raquel Gómez", "text": "x"}) == ("b0-i1", False)


def test_one_answer_runs_its_act_once_whoever_triggers_it(fresh):
    ask_id = _held()
    assert inline_ask.claim("mensajeria", "send_to", {"contact": "Raquel Gómez", "text": "x"}) == ("b0-i1", False)
    entry = dict(asker.artefact("b0-i1"), state="pending")      # a racing trigger that read the artefact before
    assert asyncio.run(inline_ask.rerun("b0-i1", entry, "la primera", 0)) is None
    assert fresh.ran == [], "the model's own call took the answer: the verdict's re-run sends nothing"
    assert inline_ask.take(ask_id) is False


def test_an_act_that_already_reached_the_candidate_is_not_repeated(fresh):
    ask_id = _held()
    inline_ask.reached("mensajeria", "send_to", {"ok": True, "result": {"to": "Raquel Gómez"}}, "b0-i2")
    asyncio.run(worker_api.answer(ask_id, "la primera", choice=0))
    assert fresh.ran == [], "the same turn's act already reached Raquel Gómez on another row"
    assert ts.task_get("b0-i1")["state"] == "done"
