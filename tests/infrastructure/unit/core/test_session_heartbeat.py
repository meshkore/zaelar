"""
SESSION HEARTBEAT to the control plane (2026-08-15, operator proposal after reviewing the liveness of a cloud
account): `identity.end_session()` is best-effort — if the Machine dies abruptly, it never arrives — and the
back office had to GUESS "is this account still alive?" from the timestamp of the most recent event in the
account's own SQLite database (noisy: homeostasis/cron count the same as real activity). Instead of a new
channel, `begin_session()` repeats the same "start" notice that already updates `last_seen_at` in the control
plane (`userSessions.touch`, idempotent) every `_HEARTBEAT_INTERVAL_S` while the session remains open, and
`end_session()` cancels it. These tests cover that task's lifecycle, not the HTTP transport
(`_report_to_control_plane` already has its own no-op guard, tested separately).
"""
from __future__ import annotations

import asyncio

import pytest

from observability import identity


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(identity, "_session", {"id": None, "started_ms": None, "source": ""})
    monkeypatch.setattr(identity, "_emit_session", lambda *a, **k: None)
    monkeypatch.setattr(identity, "_heartbeat", {"task": None})
    yield
    identity._stop_heartbeat()


def test_begin_session_starts_a_heartbeat_task_when_a_loop_is_running(monkeypatch):
    monkeypatch.setattr(identity, "_report_to_control_plane", lambda *a, **k: None)

    async def run():
        identity.begin_session(source="test", force=True)
        assert identity._heartbeat["task"] is not None
        assert isinstance(identity._heartbeat["task"], asyncio.Task)
        assert not identity._heartbeat["task"].done()

    asyncio.run(run())


def test_end_session_cancels_the_heartbeat_task(monkeypatch):
    monkeypatch.setattr(identity, "_report_to_control_plane", lambda *a, **k: None)

    async def run():
        identity.begin_session(source="test", force=True)
        task = identity._heartbeat["task"]
        identity.end_session("test")
        assert identity._heartbeat["task"] is None
        await asyncio.sleep(0)               # let a tick run so the cancellation can propagate
        assert task.cancelled() or task.done()

    asyncio.run(run())


def test_begin_session_without_a_running_loop_does_not_crash():
    """Outside a loop (startup, a synchronous test) there is no one to launch a task for — it must not crash,
    and there is simply no heartbeat to maintain."""
    info = identity.begin_session(source="test", force=True)
    assert info.get("id")
    assert identity._heartbeat["task"] is None


def test_the_heartbeat_loop_repeats_the_start_report_while_the_session_stays_open(monkeypatch):
    calls = []
    monkeypatch.setattr(identity, "_report_to_control_plane", lambda label, info: calls.append(label))
    monkeypatch.setattr(identity, "_HEARTBEAT_INTERVAL_S", 0.01)

    async def run():
        identity.begin_session(source="test", force=True)
        await asyncio.sleep(0.05)            # more than enough intervals
        identity.end_session("test")

    asyncio.run(run())
    assert calls.count("start") >= 2, f"esperaba varios latidos, solo hubo {calls}"


def test_a_second_begin_session_does_not_leak_a_previous_heartbeat_task(monkeypatch):
    """`begin_session(force=True)` can be called twice without going through `end_session` (e.g. a reset). The
    previous task must not remain alive in the background, beating for a session that no longer exists."""
    monkeypatch.setattr(identity, "_report_to_control_plane", lambda *a, **k: None)

    async def run():
        identity.begin_session(source="test", force=True)
        first = identity._heartbeat["task"]
        identity.begin_session(source="test", force=True)
        second = identity._heartbeat["task"]
        assert second is not first
        await asyncio.sleep(0)
        assert first.cancelled() or first.done()

    asyncio.run(run())
