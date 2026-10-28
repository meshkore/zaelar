"""A real `WorkerSession` on a dummy backend, for guards that read what a session DOES (refactor2710-09).

Guards on `workers/session.py` used to read its source — «`_harness(rec` comes before `await _deliver(rec)`»,
«the chip text is in this slice». A split of the session moved those lines and left the guards reading nothing.
This is the door instead: the real `_on_event` and `_finish` run against a session whose backend does nothing,
with the chips, the bus and the delivery captured.
"""
from __future__ import annotations

import asyncio

from nucleo.workers import session as S
from nucleo.workers.base import WorkerEvent, WorkerSpec


class _Backend:
    async def stop(self):
        return None


def session(monkeypatch, **rec) -> S.WorkerSession:
    """A session whose chips land in `.chips` [(phase, label, ok, extra)] and bus topics in `.buses`."""
    record = S.SessionRecord(task_id=rec.pop("task_id", "t-door"), goal=rec.pop("goal", "carpinteros en Soria"))
    for k, v in rec.items():
        setattr(record, k, v)
    s = S.WorkerSession(_Backend(), WorkerSpec(task_id=record.task_id), record)
    s.chips, s.buses = [], []
    monkeypatch.setattr(s, "_emit_chip", lambda phase, label="", ok=True, extra=None:
                        s.chips.append((phase, label, ok, dict(extra or {}))), raising=False)
    monkeypatch.setattr(s, "_bus", lambda topic, payload: s.buses.append((topic, dict(payload))), raising=False)
    return s


def event(s: S.WorkerSession, etype: str, **data) -> None:
    s._on_event(WorkerEvent(task_id=s._rec.task_id, type=etype, data=data, backend="dummy"))


def finish(monkeypatch, s: S.WorkerSession, *, harness=None) -> list:
    """Run `_finish` with relay/restart quiet and the delivery captured. Returns the ORDER of what happened:
    `("harness", ok)` when the end state is judged and `("deliver", summary)` when the operator is told."""
    order: list = []

    def _harness(rec, cap):
        order.append(("harness", rec.ok))
        if harness:
            harness(rec)

    async def _deliver(rec):
        order.append(("deliver", rec.result_summary))

    monkeypatch.setattr(S, "_relay_out_of_fuel", lambda rec, cap: None)
    monkeypatch.setattr(S, "_restart_stalled", lambda rec: None)
    monkeypatch.setattr(S, "_harness", _harness)
    monkeypatch.setattr(S, "_deliver", _deliver)
    s._stopped = True
    asyncio.run(s._finish())
    return order
