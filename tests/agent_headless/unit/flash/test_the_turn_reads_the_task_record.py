"""V2-776 D3 — FlashBrain reads the durable task record, so «still being built» cannot outlive the worker.

Measured 2026-09-27 (session 3a9a082c, 15:46): «Have you finished?» → «Not yet — the accountancy widget is
still being built». The worker had died at 12:50; RAM keeps an ending for five minutes; the only source left
was the model's own unkept promise. The row said `failed` the whole time.

V2-776 M2 (2026-09-30): the record no longer speaks only when RAM is silent — it is the block of recent requests,
always (`task_block.recent_lines`). A live worker keeps its own richer block; its row is not repeated.
"""
from __future__ import annotations

import time

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import dispatch
from nucleo.flash import prompt


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    yield
    memdb.reset_db()


def _ended(uid, *, hours_ago, state="failed", visible=True, outcome="No pude crear el widget."):
    t = int(time.time() - hours_ago * 3600)
    ts.task_put({"id": uid, "title": "Widget de contabilidad para Richard", "goal": "g", "state": state,
                 "visible": visible, "created_at": t - 60, "started_at": t - 60, "finished_at": t,
                 "outcome": outcome})


def test_hours_later_the_turn_still_knows_the_widget_failed(fresh_db):
    _ended("abcdef-8", hours_ago=3)
    state = prompt.live_state()
    assert "LO ÚLTIMO QUE TE HA PEDIDO" in state
    assert "Widget de contabilidad" in state and "FALLÓ" in state and "No pude crear el widget" in state


def test_a_live_worker_does_not_silence_the_record_any_more(fresh_db, monkeypatch):
    _ended("abcdef-8", hours_ago=3)
    monkeypatch.setattr(dispatch, "pending_summaries",
                        lambda: [{"request": "búscame piso", "phase": "mirando", "id": "1"}])
    assert "Widget de contabilidad" in prompt.live_state()


def test_old_or_internal_work_is_not_quoted(fresh_db):
    _ended("abcdef-1", hours_ago=30)
    _ended("abcdef-2", hours_ago=1, visible=False)          # the engine talking to itself
    assert "LO ÚLTIMO QUE TE HA PEDIDO" not in prompt.live_state()
