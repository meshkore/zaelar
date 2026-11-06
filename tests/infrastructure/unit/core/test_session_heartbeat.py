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


import pytest

from observability import identity


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(identity, "_session", {"id": None, "started_ms": None, "source": ""})
    monkeypatch.setattr(identity, "_emit_session", lambda *a, **k: None)
    monkeypatch.setattr(identity, "_heartbeat", {"task": None})
    yield
    identity._stop_heartbeat()


def test_begin_session_without_a_running_loop_does_not_crash():
    """Outside a loop (startup, a synchronous test) there is no one to launch a task for — it must not crash,
    and there is simply no heartbeat to maintain."""
    info = identity.begin_session(source="test", force=True)
    assert info.get("id")
    assert identity._heartbeat["task"] is None
