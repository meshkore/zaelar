"""V2-776 D1 — the durable task row says what is really happening, or nothing can supervise from it.

Measured 2026-09-27 (session 3a9a082c): two accountancy-widget rows sat `pending` for hours. Each had stopped
at the widget confirmation gate; the operator said «Yes», a NEW commission ran and died, and the gated row was
never closed — every early return of `_run_session` skipped `tasks.closed()`. The same session showed the
other half: a normal errand's row read `pending` for its whole run, because nothing moved it to `running`.

These drive the REAL listener (the fake backend of `test_a_commission_leaves_a_durable_row`), plus the pulse.
"""
from __future__ import annotations

import asyncio
import time

import bus
from memory import tasks_store as ts
from nucleo import dispatch
from nucleo import tasks as T
from tests.agent_headless.unit.test_a_commission_leaves_a_durable_row import (  # noqa: F401 — fixtures
    _commission, _hash_backend, _no_sessions_left_behind, fresh_db)
from tests.waiting import until


def test_a_worker_at_work_reads_running_not_pending(fresh_db, monkeypatch):
    """The store is what the pulse and FlashBrain read (D2/D3): «queued» for a live worker is a lie."""
    seen = {}

    def _look():
        rows = ts.tasks_where(states=ts.LIVE_STATES, visible_only=False)
        seen["state"] = rows[0]["state"] if rows else None

    async def _go():
        # The row is written at dispatch and the worker starts a beat later — wait for the start itself.
        live, _ = await _commission(monkeypatch, "búscame piso de alquiler en Gràcia", release=False)
        await until(lambda: (lambda r: r if r and r[0]["state"] == "running" else None)(
            ts.tasks_where(states=ts.LIVE_STATES, visible_only=False)),
            "the row to say the worker started", timeout_s=5)
        _look()
    asyncio.run(_go())
    assert seen["state"] == "running"


def test_a_commission_stopped_at_the_widget_gate_leaves_no_live_row(fresh_db, monkeypatch):
    """The gate asks; the «sí» dispatches a fresh commission with its own row. The asked one must not linger."""
    from nucleo.flash import escalate

    async def _quiet(rec):
        return None
    monkeypatch.setattr(dispatch, "_deliver_confirm", _quiet)
    asked = {}
    real_remember = dispatch.remember_code_change

    def _remember(*a, **k):
        asked["row_then"] = ts.tasks_where(states=ts.LIVE_STATES, visible_only=False)
        return real_remember(*a, **k)
    monkeypatch.setattr(dispatch, "remember_code_change", _remember)

    async def _go():
        bus.reset()
        escalate.reset()
        stop = asyncio.Event()
        listener = asyncio.create_task(dispatch.run_listener(stop))
        await asyncio.sleep(0.05)
        escalate.escalate_to_slowbrain("hazme un widget de contabilidad", context={"kind": "code"})
        await until(lambda: True if "row_then" in asked and not dispatch._SESSIONS else None,
                    "the widget gate to ask", timeout_s=5)
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.sleep(0.05)
        listener.cancel()
    asyncio.run(_go())
    assert asked["row_then"], "the gate asked before any row existed — this test would prove nothing"
    assert ts.tasks_where(states=ts.LIVE_STATES, visible_only=False) == []


def _row(uid, *, age_s=0.0, state="pending", **kw):
    now = int(time.time())
    ts.task_put({"id": uid, "goal": "x", "state": state, "created_at": now - int(age_s),
                 "started_at": now - int(age_s), **kw})


def test_the_reconciler_settles_orphans_and_only_worker_rows(fresh_db):
    boot = T._boot_id()
    _row(f"{boot}-4", age_s=600)                       # the 2026-09-27 ghost: nobody carries it
    _row(f"{boot}-5", age_s=10)                        # a relay in the air: inside the grace window
    _row(f"{boot}-6", age_s=600, state="running")      # alive and carried
    _row("abcdef-2", age_s=600, state="running")       # a previous boot: nothing can still be running it
    _row("lista:20260927-120000-ab12", age_s=600)      # a list has its own owner (V2-771)
    _row("errand:9", age_s=600, state="running")       # an errand's silence is not a stalled worker
    assert T.reconciled({f"{boot}-6"}) == 2
    get = lambda i: ts.task_get(i)["state"]            # noqa: E731
    assert get(f"{boot}-4") == "failed"
    assert "reinicio" in ts.task_get("abcdef-2")["outcome"]
    assert get(f"{boot}-5") == "pending"
    assert get(f"{boot}-6") == "running"
    assert get("lista:20260927-120000-ab12") == "pending"
    assert get("errand:9") == "running"


def test_the_pulse_runs_the_reconciler(fresh_db):
    """The wiring, not the function: a reconciler nobody calls is how the ghosts of 2026-09-27 survived."""
    from nucleo.loop import OrchestratorLoop
    boot = T._boot_id()
    _row(f"{boot}-7", age_s=600)

    async def _noop(*a, **k):
        return None
    loop = OrchestratorLoop(deliver=_noop)
    asyncio.run(loop._supervise_workers(time.time()))
    assert ts.task_get(f"{boot}-7")["state"] == "failed"


def test_a_finished_worker_still_speaking_its_delivery_is_not_an_orphan(fresh_db, monkeypatch):
    """Demo pass 2026-09-28, S1: the monitors search was `done` and waiting for a moment to SPEAK its delivery
    (still in `_SESSIONS`, its row not yet closed). The pulse read only LIVE statuses, settled the row as «failed
    — nobody was carrying it», and the FlashBrain told him the finished search had failed and ran it again."""
    from types import SimpleNamespace
    from nucleo.loop import OrchestratorLoop
    boot = T._boot_id()
    _row(f"{boot}-8", age_s=600, state="running")
    rec = SimpleNamespace(uid=f"{boot}-8", status="done", task_id=8, kind="web", backend="", goal="x")
    monkeypatch.setitem(dispatch._SESSIONS, "8", rec)

    async def _noop(*a, **k):
        return None
    loop = OrchestratorLoop(deliver=_noop)
    loop._last_reconcile = 0
    try:
        asyncio.run(loop._supervise_workers(time.time()))
    except Exception:  # noqa: BLE001 — the fake record is only what the reconciler reads
        pass
    assert ts.task_get(f"{boot}-8")["state"] == "running", "a delivery in progress was settled as an orphan"
