"""Where a WORK SESSION begins and ends — the boundaries, not the contents (2026-08-31).

The operator pressed ⏻ off, then Reset, and the master showed a session "EN CURSO" (7 events, 0 flows) on an
engine whose own switch said `stopped`. Two independent defects met there, and both are about a BOUNDARY:

  1. **A reset opened a session in front of a stopped agent.** `voice/observer.py::stamp_identity` has refused
     to let an EVENT self-open a session while stopped since 2026-08-16, but `rotate_session` called
     `identity.begin_session(force=True)` explicitly and walked straight past that guard. The session then sat
     open forever holding nothing but the browser tab's own noise.
  2. **No session ever recorded its own end.** `end_session` clears `_session["id"]` before emitting the closing
     mark, so `stamp_identity` — correctly — would not invent a session for that `system` event, the event went
     out with an empty `sid`, and `observer._session_path("")` dropped it. Measured on the operator's engine:
     ZERO of the last twelve session files contained a `session/end` record, so auditing a session could never
     say how or why it ended.

And the rule that ties them together, which is what the operator asked for: **stopping ENDS the session,
starting BEGINS a new one** — the session is the span in which the agent could work, so nothing else may open
one, and an idle stretch closes it on its own instead of leaving it open forever.
"""
import asyncio
import time

import pytest

from memory import db as memdb
from observability import identity
from voice import observer

_END_SESSION = identity.end_session


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    """Neither the timeline nor the control-plane is the subject here: silence both so a test never touches the
    network or the operator's real log, and leave the switch RUNNING for whoever comes next.

    And a database of its OWN. Two tests here drive `runstate.stop()`/`start()` for real, and `_persist` writes
    the switch to `sys_kv` — the OPERATOR's `sys_kv` without this, which is not a hypothetical: the first run of
    this file left his engine persisted as `stopped` with `src="test"`, and a restart obeyed it. The root
    conftest only resets the in-process CACHE (it says so); pointing `ZAELAR_DB` at a temp file is the other half,
    the same one `tests/agent_headless/unit/test_runstate.py` has always used. A unit test never touches a live
    artefact."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    monkeypatch.setattr(identity, "_report_to_control_plane", lambda *a, **k: None)
    monkeypatch.setattr(identity, "_bill_transport", lambda *a, **k: None)
    _END_SESSION("test")
    observer.clear_log()
    yield
    _END_SESSION("test")
    observer.clear_log()
    _running()
    memdb.reset_db()


def _stopped():
    from nucleo import runstate
    runstate._state.update({"value": runstate.STOPPED, "at": time.time(), "src": "test"})


def _running():
    from nucleo import runstate
    runstate._state.update({"value": runstate.RUNNING, "at": time.time(), "src": "test"})


# ── 1. nothing opens a session while the agent is stopped ────────────────────────────────────────────────
def test_a_stopped_agent_does_not_get_a_session_from_begin_session():
    _stopped()
    assert identity.begin_session(source="frontend") == {}
    assert not identity.session_info()["session_id"], \
        "«parar es parar»: with the switch off there is no tramo in which the agent could be working"


def test_a_reset_in_front_of_a_stopped_agent_opens_no_session():
    """The operator's exact gesture: ⏻ off, then Reset. The blank slate still happens — what must NOT happen is
    a brand-new session left open, which is what the master then reports as EN CURSO."""
    _running()
    observer.emit("test", "work", text="something from the session that is about to be stopped")
    _stopped()
    assert observer.rotate_session("reset") == {}
    assert not identity.session_info()["session_id"]
    assert not any((e.get("label") or "") == "work" for e in observer._events), \
        "the reset still wipes the slate — refusing to open a session is not refusing to reset"


def test_a_running_agent_still_gets_its_new_session_on_reset():
    """The counterweight, and the reason the guard reads the switch instead of just never opening: with the
    agent running, a deliberate reset is still «stop it and start it again», new id and all (2026-08-10)."""
    _running()
    before = identity.session_id()
    info = observer.rotate_session("reset")
    assert info.get("session_id") and info["session_id"] != before


# ── 2. ⏻ ON is what starts the next session ──────────────────────────────────────────────────────────────
def test_powering_the_agent_on_opens_a_new_work_session():
    """The mirror image of the close in `_do_stop`. Without this the operator's model («I turned it back on, so
    this is a new session») held only by accident, through whichever background event happened to land first."""
    from nucleo import runstate
    _stopped()
    assert not identity.session_info()["session_id"]
    asyncio.run(runstate.start("test"))
    sid = identity.session_info()["session_id"]
    assert sid, "⏻ ON has to open the tramo it just made possible"
    assert identity.session_info()["source"] == "power_on", \
        "and say who opened it — an audit that cannot tell a power-on from a tab reload cannot explain the gap"


def test_stopping_the_agent_closes_the_session_it_opened():
    from nucleo import runstate
    _running()
    identity.begin_session(source="test", force=True)
    assert identity.session_info()["session_id"]
    asyncio.run(runstate.stop("test"))
    assert not identity.session_info()["session_id"]


# ── 3. the closing mark lands in the file of the session it closes ───────────────────────────────────────
def test_the_closing_event_carries_the_session_it_closes():
    """`sid`, not just `session_id` in the payload: `sid` is the field `observer._session_path` routes by, so
    with it empty the closing mark was written to no session file at all."""
    _running()
    sid = identity.begin_session(source="test", force=True)["id"]
    observer.clear_log()
    identity.end_session("power_off")
    ends = [e for e in observer._events if e.get("kind") == "session" and e.get("label") == "end"]
    assert ends, "closing a session has to emit its closing mark"
    assert ends[-1].get("sid") == sid, \
        "an end stamped with an empty sid never reaches the file of the session it closes"
    assert ends[-1].get("reason") == "power_off", "and it has to say WHY — that is the whole point of auditing it"


def test_the_closing_event_is_written_to_that_sessions_own_file():
    """The end-to-end version of the one above, through the routing that actually dropped it: `_session_path`."""
    _running()
    sid = identity.begin_session(source="test", force=True)["id"]
    identity.end_session("power_off")
    ends = [e for e in observer._events if e.get("kind") == "session" and e.get("label") == "end"]
    assert observer._session_path(ends[-1].get("sid")).endswith(f"{sid}.jsonl")


# ── 4. an abandoned session closes on its own ────────────────────────────────────────────────────────────
def test_an_idle_session_closes_without_waiting_for_activity_to_come_back():
    """`note_real_activity` can only fire when activity RETURNS, so a session nobody comes back to stayed open
    forever. `close_if_idle` is the same decision taken from the other side, and the pulse offers it."""
    _running()
    identity.begin_session(source="test", force=True)
    identity._session["started_ms"] = round(time.time() * 1000) - identity.IDLE_TIMEOUT_MS - 1000
    identity._last_real_activity_ms["v"] = None
    assert identity.close_if_idle() is True
    assert not identity.session_info()["session_id"]


def test_a_fresh_session_is_not_born_already_expired():
    """`_last_real_activity_ms` is global, not per-session: a session opened after a long quiet stretch would be
    killed by the previous stretch's clock if the start time were not taken into account."""
    _running()
    identity._last_real_activity_ms["v"] = round(time.time() * 1000) - identity.IDLE_TIMEOUT_MS - 60_000
    identity.begin_session(source="test", force=True)
    assert identity.close_if_idle() is False
    assert identity.session_info()["session_id"], "a session that has just opened has not been idle for anything"


def test_closing_an_idle_session_twice_is_a_no_op():
    """The pulse offers this ~1 Hz: it must close ONCE and then have nothing left to do — never a rotation per tick."""
    _running()
    identity.begin_session(source="test", force=True)
    identity._session["started_ms"] = round(time.time() * 1000) - identity.IDLE_TIMEOUT_MS - 1000
    assert identity.close_if_idle() is True
    assert identity.close_if_idle() is False
