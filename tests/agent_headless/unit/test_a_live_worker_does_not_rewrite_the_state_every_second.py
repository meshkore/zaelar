"""A live worker does not rewrite the memory state every second (V2-789).

`dispatch.sync_state` runs on every loop tick (~1 Hz) and writes `activity`/`sessions` into the memory state, and
every write emits `memory.updated` → one `memory`/`state` event in the timeline. It skipped unchanged ticks by
comparing the projection minus a hand-kept list of clock fields (`age_s`, `silent_s`…). `unreported_s`, added
later, was not on the list, so one live — or paused — worker produced a state event per second for as long as it
lived (measured: ~170 in three minutes with the agent powered off). The change key is now the projection with the
clock FROZEN, so any field derived from the clock is stable by construction.

Disarm: compute the change key from the live projection again (`stable = sess`) → red.
"""
from __future__ import annotations

import types

import pytest


@pytest.fixture
def harness(monkeypatch):
    from memory import api as memapi
    from nucleo import dispatch
    from nucleo.pulse import rehydrate
    clock = [1_000_000.0]
    writes = []
    monkeypatch.setattr(dispatch, "time", types.SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(memapi, "set_state", lambda fields: writes.append(fields) or fields)
    monkeypatch.setattr(rehydrate, "remember", lambda sess: None)
    dispatch._SESSIONS.clear()
    dispatch._last_sync = None
    yield dispatch, clock, writes
    dispatch._SESSIONS.clear()
    dispatch._last_sync = None


def _rec(tid, **kw):
    from nucleo.workers.session import SessionRecord
    base = dict(task_id=tid, goal="find a second-hand sailboat", kind="web", status="running", phase="searching")
    base.update(kw)
    r = SessionRecord(**base)
    r.started = 1_000_000.0 - 30
    return r


@pytest.mark.parametrize("records", [
    [{"tid": "1"}],                                              # one worker that never reported
    [{"tid": "1", "paused": True}],                              # a worker paused by the power switch
    [{"tid": "1"}, {"tid": "2", "kind": "code", "goal": "rewrite the agenda card", "phase": "editing"}],
])
def test_ticks_with_nothing_new_write_the_state_once(harness, records):
    dispatch, clock, writes = harness
    for spec in records:
        spec = dict(spec)
        tid = spec.pop("tid")
        dispatch._SESSIONS[tid] = _rec(tid, **spec)
    for _ in range(12):
        dispatch.sync_state()
        clock[0] += 1.0
    assert len(writes) == 1, f"{len(writes)} state writes in 12 quiet ticks"


def test_a_real_change_is_still_written_with_the_live_clock(harness):
    dispatch, clock, writes = harness
    dispatch._SESSIONS["1"] = _rec("1")
    dispatch.sync_state()
    clock[0] += 5.0
    dispatch._SESSIONS["1"].phase = "reading the listing"
    dispatch.sync_state()
    assert len(writes) == 2
    assert writes[-1]["activity"] == ["reading the listing"]
    assert writes[-1]["sessions"][0]["age_s"] == 35          # what is WRITTEN keeps the real elapsed time


def test_a_worker_that_ends_is_written(harness):
    dispatch, clock, writes = harness
    dispatch._SESSIONS["1"] = _rec("1")
    dispatch.sync_state()
    dispatch._SESSIONS["1"].status = "done"
    clock[0] += 1.0
    dispatch.sync_state()
    assert len(writes) == 2 and writes[-1]["sessions"] == []
