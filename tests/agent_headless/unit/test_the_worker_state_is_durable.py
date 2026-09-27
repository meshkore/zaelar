"""V2-776 D1 — a Brain Worker's live state (phase, progress, heartbeat, last self-report) lives in its row.

Before this it lived only in RAM (`dispatch._SESSIONS`): a restart emptied it, the Master could not read it,
and the only durable fact was `state` — which read `pending` for the whole run. The operator's ask
(2026-09-27): «ese estado debe ser consultable por FlashBrain y sobre todo el bucle del pulso».
"""
from __future__ import annotations

import asyncio
import sqlite3
import time

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import dispatch
from tests.agent_headless.unit.test_a_commission_leaves_a_durable_row import (  # noqa: F401 — fixtures
    _commission, _hash_backend, _no_sessions_left_behind, fresh_db)


def test_an_existing_database_gains_the_state_columns(tmp_path, monkeypatch):
    """The operator's `zaelar.db` is v7: the columns arrive by ALTER, never by recreating the table."""
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT, goal TEXT NOT NULL, kind TEXT NOT NULL "
                "DEFAULT 'generic', mode TEXT NOT NULL DEFAULT 'now', state TEXT NOT NULL DEFAULT 'pending', "
                "visible INTEGER NOT NULL DEFAULT 1, origin TEXT NOT NULL DEFAULT 'voz', schedule TEXT, "
                "surface TEXT, sheet TEXT, trace_id TEXT, parent_id TEXT, outcome TEXT, created_at INTEGER NOT "
                "NULL, started_at INTEGER, due_at INTEGER, finished_at INTEGER)")
    con.execute("INSERT INTO tasks (id, goal, created_at) VALUES ('abcdef-1', 'kept', 1)")
    con.execute("PRAGMA user_version=7")
    con.commit()
    con.close()
    monkeypatch.setenv("ZAELAR_DB", str(path))
    memdb.reset_db()
    try:
        memdb.get_db()
        ts.task_patch("abcdef-1", phase="mirando", progress={"done": 1, "total": 3}, attempts=1)
        row = ts.task_get("abcdef-1")
        assert row["goal"] == "kept"
        assert row["phase"] == "mirando" and row["progress"] == {"done": 1, "total": 3} and row["attempts"] == 1
    finally:
        memdb.reset_db()


def test_the_pulse_beat_writes_the_workers_state_into_its_row(fresh_db, monkeypatch):
    from nucleo.loop import OrchestratorLoop

    async def _noop(*a, **k):
        return None

    async def _go():
        live, _ = await _commission(monkeypatch, "búscame piso de alquiler en Gràcia", release=False)
        uid = live[0]["id"]
        tid = next(iter(dispatch._SESSIONS))
        dispatch.session_plan(tid, "buscar|comparar|entregar")
        dispatch.session_progress(tid, "comparando precios", done=1)
        dispatch.session_phase(tid, "comparando precios")
        dispatch.session_reported(tid)
        await OrchestratorLoop(deliver=_noop)._supervise_workers(time.time())
        return ts.task_get(uid)
    row = asyncio.run(_go())
    assert row["phase"] == "comparando precios"
    assert row["progress"]["done"] == 1 and row["progress"]["total"] == 3
    assert row["heartbeat_at"] and row["heartbeat_at"] >= int(time.time()) - 60
    assert row["reported_at"] and row["reported_at"] >= int(time.time()) - 60


def test_a_worker_report_sets_its_self_report_clock(fresh_db, monkeypatch):
    """`hbnote` is the worker speaking for itself; that — not any stream event — is what the clock counts."""
    from nucleo import agent_api

    async def _go():
        await _commission(monkeypatch, "búscame piso en Gràcia", release=False)
        tid = next(iter(dispatch._SESSIONS))
        before = dispatch.get_record(tid).reported_at
        await agent_api.agent_report(tid=tid, token="", phase="leyendo anuncios", note="", plan="",
                                     progress=None, done=None, pct=None, considered=None, kept=None,
                                     done_when=None)
        return before, dispatch.get_record(tid).reported_at
    before, after = asyncio.run(_go())
    assert before == 0.0
    assert after > 0.0
