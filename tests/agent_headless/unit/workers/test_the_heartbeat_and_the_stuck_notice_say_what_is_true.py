"""The heartbeat and the «no sign of life» notice say only what is true (V2-831 T-19 R14).

Demo pass 3, F2 (sandbox build 86): the Bitcoin-summary worker read a page for 42 s; after the read returned it sent
nothing for 183 s. Through those three minutes the pulse's own heartbeat kept saying «reading nakamotoinstitute.org —
2 min so far», because the phase a tool call sets outlived the call. Then the notice said «If it doesn't react in a
couple of minutes I'll restart it once» whatever the supervisor would actually do.

Three classes, one test each:
  · a phase set by a tool call ends with that call (`session_events`, on its `step_result`);
  · ANY report the worker sends — a note alone included — moves the one «last signal» clock (`session_reported`),
    so a worker that only reports is not stuck, and a truly silent one is;
  · the notice reads the supervisor's real decision (`relay.restarts_left`, `stall._STALL_S`): restart / stop / watch.

Disarms: drop the step_result restore → the heartbeat test reds; drop `last_event_at` from `session_reported` →
the reporting-worker test reds; make the notice always use `worker_stuck` → the decision test reds.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import dispatch
from nucleo.pulse import loop as L
from nucleo.workers import reports, session_events, stall as stall_mod
from nucleo.workers.session import SessionRecord, _default_label


def _session(rec):
    """The event handler's `self`: the record plus the no-op surfaces it writes to."""
    noop = lambda *a, **k: None  # noqa: E731
    return SimpleNamespace(_rec=rec, _bus=noop, _emit_chip=noop, _emit_step=noop, _emit_step_result=noop,
                           _maybe_unstick_permission=noop, _maybe_hand_web=noop, _spin={})


def _ev(kind, **data):
    return SimpleNamespace(type=kind, data=data)


def test_the_phase_a_tool_call_set_ends_when_the_call_returns(monkeypatch):
    rec = SessionRecord(task_id="3", goal="one-page Bitcoin summary", kind="research", status="running")
    s = _session(rec)
    session_events._on_event(s, _ev("phase", label="reading nakamotoinstitute.org…", quiet=True))
    assert rec.phase == "reading nakamotoinstitute.org…"
    session_events._on_event(s, _ev("step_result", text="# Bitcoin Whitepaper Report …", tool="Bash"))
    assert "nakamotoinstitute" not in rec.phase, f"the heartbeat still says the read is going on: {rec.phase!r}"
    assert rec.phase == _default_label("research")
    monkeypatch.setattr(dispatch, "_SESSIONS", {"3": rec})
    rec.last_event_at = time.time() - 150
    assert "nakamotoinstitute" not in reports.session_alive("3")


def test_a_phase_the_worker_set_itself_survives_a_tool_result():
    """Only the TOOL's phase ends with the tool: a phase the worker reported (`hbnote`) is not overwritten."""
    rec = SessionRecord(task_id="4", goal="x", status="running")
    s = _session(rec)
    session_events._on_event(s, _ev("phase", label="running a step…"))
    rec.phase = "drafting the report"                 # what `reports.session_phase` writes on an hbnote
    session_events._on_event(s, _ev("step_result", text="(Bash completed with no output)"))
    assert rec.phase == "drafting the report"


def _say_collector():
    said = []

    async def _deliver(title, text, **kw):
        said.append((text, kw.get("key")))
    return said, _deliver


def test_a_worker_that_only_reports_is_alive_and_a_silent_one_is_not(monkeypatch):
    said, deliver = _say_collector()
    talking = SessionRecord(task_id="6", goal="only notes", status="running", backend="claude_code")
    silent = SessionRecord(task_id="7", goal="truly silent", status="running", backend="claude_code")
    for r in (talking, silent):
        r.started = r.last_event_at = time.time() - dispatch.STUCK_SECS - 60
        r.session = SimpleNamespace(inject=lambda t: asyncio.sleep(0))
    monkeypatch.setattr(dispatch, "_SESSIONS", {"6": talking, "7": silent})
    reports.session_reported("6")                     # a note-only `/api/agent/report`
    asyncio.run(L.OrchestratorLoop(deliver=deliver)._supervise_workers(time.time()))
    keys = {k for _, k in said}
    assert L._STUCK_KEY + "6" not in keys, "a worker that keeps reporting was declared without signs of life"
    assert L._STUCK_KEY + "7" in keys, "a truly silent worker was not announced"


def test_every_report_goes_through_the_clock_door():
    """`/api/agent/report` stamps the clock before reading which fields came — so a note-only report counts."""
    import inspect
    from nucleo import agent_api
    src = inspect.getsource(agent_api.agent_report)
    i = src.index("dispatch.session_reported(tid)")
    assert i < src.index("if phase.strip():"), "the clock is stamped only for some kinds of report"


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


@pytest.mark.parametrize("attempts,stall_s,expect", [
    (0, 300.0, "worker_stuck"),          # it will be restarted once
    (1, 300.0, "worker_stuck_stop"),     # the restart is spent: it will only be stopped
    (0, 0.0, "worker_stuck_watch"),      # no watchdog: nothing will act on it
])
def test_the_notice_says_what_the_supervisor_will_do(fresh_db, monkeypatch, attempts, stall_s, expect):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    monkeypatch.setattr(stall_mod, "_STALL_S", stall_s)
    ts.task_put({"id": "uid-8", "goal": "summary", "state": "running", "created_at": int(time.time())})
    ts.task_patch("uid-8", attempts=attempts)
    rec = SessionRecord(task_id="8", goal="Bitcoin summary", uid="uid-8", status="running", backend="widget_generator")
    rec.started = rec.last_event_at = time.time() - 180
    monkeypatch.setattr(dispatch, "_SESSIONS", {"8": rec})
    said, deliver = _say_collector()
    lp = L.OrchestratorLoop(deliver=deliver)
    asyncio.run(lp._supervise_workers(time.time()))
    stuck = [t for t, k in said if k == L._STUCK_KEY + "8"]
    assert len(stuck) == 1
    want = lp._say(expect, goal="Bitcoin summary", minutes=3, left=2)
    assert stuck[0] == want, f"said {stuck[0]!r}, the supervisor's decision reads {want!r}"
    if expect != "worker_stuck":
        assert "restart it" not in stuck[0], "a restart was promised that the supervisor will not do"
