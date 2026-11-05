"""What the session header counts, the viewer lists — with the flow of each row (V2-852 T16).

The first live session on the task engine: the header said 21 errors and 2 failed tasks; the event list showed 3
`kind=error`. The other 18 were health `alert` rows with no `corr_id` — counted by the summary, in no flow, so no
reader could open them. `observability.flows.faults()` lists the rows behind both counters with the SAME predicates
(`ERROR_WHERE`, `FAILED_TASK_WHERE`), and the session route serves them as `faults`.

Disarm: narrow `faults()`'s WHERE to the error predicate alone → the failed task is counted and not listed → red.
"""
from __future__ import annotations

import time

import pytest


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    import bus
    from bus import log as _log
    _log._conn = None
    _log.detach(bus)
    _log.attach(bus)
    from observability import identity as _ident
    _ident._user["id"] = None
    _ident._session["id"] = None
    yield _log
    _log.detach(bus)
    _log._conn = None


def test_every_counted_row_is_listed_with_its_flow(wired):
    from observability import flows, identity
    from voice import trace
    from voice.observer import emit

    identity.begin_session("test")
    sid = identity.session_id()
    emit("alert", "the engine is short of memory", role="system", extra={"cat": "health"})   # outside any flow
    emit("error", "a background loop failed", role="system")
    tid = trace.begin("find me a flat to rent in Lisbon")
    emit("error", "a tool raised", role="system")
    emit("task", "end", extra={"id": "41", "ok": False, "status": "error"})
    emit("task", "end", extra={"id": "41", "ok": False, "status": "error"})           # the same task, closed twice
    emit("task", "end", extra={"id": "42", "ok": True, "status": "done"})
    time.sleep(0.25)

    head = flows.session(sid)
    got = flows.faults(session_id=sid)
    errors = [r for r in got if r["fault"] == "error"]
    failed = {r["task_id"] for r in got if r["fault"] == "failed_task"}
    assert head["errors"] == len(errors) == 3, (head, got)
    assert head["failed_tasks"] == len(failed) == 1, (head, got)
    assert {r["corr_id"] for r in errors} == {None, tid}, "a fault outside any flow is listed, its corr_id null"
    assert all(r["corr_id"] == tid for r in got if r["fault"] == "failed_task")
    flow_row = next(f for f in flows.flows(session_id=sid) if f["corr_id"] == tid)
    assert flow_row["errors"] == len(flows.faults(corr_id=tid)) - 2 == 1


def test_the_session_route_serves_the_rows(wired, monkeypatch):
    import asyncio
    import json
    from observability import api, identity
    from voice.observer import emit
    identity.begin_session("test")
    sid = identity.session_id()
    emit("alert", "the engine has recovered", role="system", extra={"cat": "health"})
    time.sleep(0.25)
    monkeypatch.setattr(api, "_allowed", lambda request: True)
    out = json.loads(asyncio.run(api.one_session(None, sid)).body)
    assert out["errors"] == len(out["faults"]) == 1 and out["faults"][0]["kind"] == "alert"
