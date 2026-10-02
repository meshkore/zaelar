"""An inline request's row survives a restart honestly (V2-778 F3-26, 2026-10-01).

Every request that acts opens a durable row (`nucleo/request_row.py`, V2-776 M1), but its end state — the spec
the circuit re-verifies — lived only in RAM. A restart between the op and the pulse's verdict left the row
`running` FOREVER: the reconciler that closes orphaned rows matched worker ids (`<boot>-<n>`) and an inline
row is `<boot>-i<n>`, so nothing ever settled it, and «what is still going on» kept listing a request that no
process was watching. Now the inline spec is persisted on its row, and a previous boot's live inline row is
judged once from it: met if the screen shows it, otherwise closed as interrupted by the restart — no voice.
"""
from __future__ import annotations

import time

import pytest

from memory import tasks_store as ts
from nucleo import spec as S
from nucleo import tasks as T
from tests.agent_headless.unit.test_a_commission_leaves_a_durable_row import fresh_db  # noqa: F401 — fixture


def _inline_row(uid, *, age_s=600, state="running"):
    now = int(time.time())
    ts.task_put({"id": uid, "goal": "pon el vídeo", "kind": "inline", "mode": "now", "state": state,
                 "created_at": now - int(age_s), "started_at": now - int(age_s)})


def test_a_previous_boots_inline_row_with_no_spec_is_closed_as_interrupted(fresh_db):
    _inline_row("abcdef-i3")
    assert T.reconciled(set()) == 1
    row = ts.task_get("abcdef-i3")
    assert row["state"] == "failed" and "reinicio" in row["outcome"]


def test_a_previous_boots_inline_row_whose_end_state_holds_is_met(fresh_db, monkeypatch):
    _inline_row("abcdef-i4")
    S.persist("abcdef-i4", {"done_when": {"x": 1}, "status": "open", "born": time.time() - 600})
    monkeypatch.setattr(S, "attest", lambda e, now=None: True)
    assert T.reconciled(set()) == 1
    row = ts.task_get("abcdef-i4")
    assert row["state"] == "done" and row.get("verdict") == "met"


def test_this_boots_inline_rows_are_left_to_the_pulse(fresh_db):
    """The live process still holds their spec in memory: the circuit's own pulse settles them."""
    uid = f"{T._boot_id()}-i5"
    _inline_row(uid)
    assert T.reconciled(set()) == 0
    assert ts.task_get(uid)["state"] == "running"


def test_the_inline_spec_is_persisted_on_its_row(fresh_db, monkeypatch):
    """The data-op door: once the op has its row, the spec it owes is written on that row."""
    import asyncio

    from nucleo import request_row as _rq
    from nucleo.flash import data_ops
    import widgets

    monkeypatch.setattr(S, "open_for_action", lambda *a, **k: S.open({"widget": "youtube", "all": [
        {"field": "youtube.videoId", "changed": True}]}, text="pon el vídeo", widget="youtube", action="load"))
    monkeypatch.setattr(S, "attest", lambda e, now=None: False)

    async def _dispatch(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(widgets, "dispatch_tag", _dispatch)

    async def _go():
        _rq.begin("pon el vídeo")
        await data_ops.dispatch_and_report("youtube", "load", {"q": "x"}, seal=None, text="pon el vídeo", said="")
    asyncio.run(_go())
    rows = ts.tasks_where(states=ts.LIVE_STATES, visible_only=False)
    assert rows, "the op opened no row — this test would prove nothing"
    persisted = S.of_task(rows[0]["id"])
    assert persisted and persisted.get("done_when"), "the row carries no spec: a restart would orphan it"
