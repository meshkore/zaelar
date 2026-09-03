"""A work session cannot be born without announcing itself (V2-562).

There are TWO doors into a new session — the explicit `begin_session()` and the lazy self-open inside
`session_id()` — and only the first announced itself. So the central activity registry only ever received
`event="end"`, and closing a row that was never opened updates nothing: measured 2026-09-03 against the real
control-plane, `zaelar_user_sessions` held **0 rows for every account, ever**, while every `POST /session`
returned 200. The registry built to survive a Machine being destroyed was recording nobody, silently.

These tests drive the real functions and read what actually left the module — never a reimplementation of the
rule, which would keep passing while production reported nothing.
"""
import pytest

from observability import identity


@pytest.fixture()
def reported(monkeypatch):
    """Capture what would have gone to the control-plane, and keep the heartbeat off the event loop."""
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(identity, "_report_to_control_plane", lambda label, info: calls.append((label, dict(info))))
    monkeypatch.setattr(identity, "_start_heartbeat", lambda info: None)
    monkeypatch.setattr(identity, "_stop_heartbeat", lambda: None)
    monkeypatch.setattr(identity, "_emit_session", lambda *a, **k: None)
    monkeypatch.setattr(identity, "_bill_transport", lambda ms: None)
    monkeypatch.setattr(identity, "_agent_stopped", lambda: False)
    identity._session.update({"id": None, "started_ms": None, "source": ""})
    yield calls
    identity._session.update({"id": None, "started_ms": None, "source": ""})


def test_a_session_opened_lazily_reports_its_start(reported):
    """THE incident: every event self-opens a session through here, and nobody was told."""
    sid = identity.session_id()
    assert sid
    assert [label for label, _ in reported] == ["start"]
    assert reported[0][1]["id"] == sid


def test_the_explicit_door_still_reports_its_start(reported):
    info = identity.begin_session("frontend")
    assert [label for label, _ in reported] == ["start"]
    assert reported[0][1]["id"] == info["id"]


def test_the_same_session_is_announced_once_however_often_it_is_read(reported):
    """`session_id()` is called on EVERY event; announcing per read would flood the registry."""
    first = identity.session_id()
    for _ in range(5):
        assert identity.session_id() == first
    assert len(reported) == 1


def test_a_close_is_reported_for_a_session_that_was_announced(reported):
    """The pairing is the point: an `end` is only meaningful about a row a `start` created."""
    sid = identity.session_id()
    identity.end_session("test")
    assert [label for label, _ in reported] == ["start", "end"]
    assert {info["id"] for _, info in reported} == {sid}


def test_a_reopen_after_a_close_is_a_new_announced_session(reported):
    first = identity.session_id()
    identity.end_session("test")
    second = identity.session_id()
    assert second != first
    assert [label for label, _ in reported] == ["start", "end", "start"]
    assert reported[-1][1]["id"] == second


def test_a_stopped_agent_still_opens_nothing_through_the_explicit_door(monkeypatch, reported):
    """The counterweight (V2-092). Announcing more must not undo 'stopping means stopped' — without this, the
    fix above would be satisfied by announcing sessions that should never exist."""
    monkeypatch.setattr(identity, "_agent_stopped", lambda: True)
    assert identity.begin_session("reset") == {}
    assert reported == []
