"""
REAL INACTIVITY ceiling for the work session (2026-08-13, operator request: a session that remains
stopped/closed must not stay alive forever accumulating events from different work periods).

`observability.identity.note_real_activity()` is the new piece: it closes the open session if it has gone more than
`IDLE_TIMEOUT_MS` without REAL activity, and `voice.observer.stamp_identity` calls it for every event that is NOT
background noise (`system`/`pulse`) before resolving `sid`. These tests control the clock manually (without
`time.sleep`) and verify the three guarantees: it rotates after a real gap, background noise neither triggers nor
extends it, and a normal reconnection (short gap) still does not split the session in two.
"""
from __future__ import annotations

import pytest

from observability import identity
from voice import observer


@pytest.fixture(autouse=True)
def _clean_identity_state(monkeypatch):
    """Each test starts with an open session and its own clock—never the process's actual state."""
    monkeypatch.setattr(identity, "_session", {"id": "s0", "started_ms": 0, "source": "test"})
    monkeypatch.setattr(identity, "_last_real_activity_ms", {"v": 0})
    monkeypatch.setattr(identity, "IDLE_TIMEOUT_MS", 5 * 60_000)
    # `end_session`/`begin_session` emit to the observer and report to the control plane—neither must
    # touch the network or the real bus in a unit test.
    monkeypatch.setattr(identity, "_emit_session", lambda *a, **k: None)
    monkeypatch.setattr(identity, "_report_to_control_plane", lambda *a, **k: None)

    clock = {"ms": 0}
    monkeypatch.setattr(identity.time, "time", lambda: clock["ms"] / 1000)
    return clock


def _stamp(cat: str, clock: dict, ms: int) -> dict:
    clock["ms"] = ms
    ev: dict = {"kind": "brain" if cat == "flash" else cat, "cat": cat}
    observer.stamp_identity(ev)
    return ev


def test_a_real_gap_past_the_timeout_rotates_the_session(_clean_identity_state):
    clock = _clean_identity_state
    first = _stamp("flash", clock, 0)
    later = _stamp("flash", clock, 6 * 60_000)  # 6 min > 5 min ceiling
    assert first["sid"] == "s0"
    assert later["sid"] != "s0"
    assert later["sid"], "rotation leaves the NEW session already open, not orphaned"


def test_background_noise_never_extends_nor_triggers_rotation(_clean_identity_state):
    clock = _clean_identity_state
    _stamp("flash", clock, 0)
    # Pure background noise for 20 min—none of it is real activity.
    for minute in range(1, 21):
        pulse = _stamp("pulse" if minute % 2 else "system", clock, minute * 60_000)
        assert pulse["sid"] == "s0", "background noise cannot trigger a rotation on its own"
    # Nor should it have extended the clock: real activity arriving after the same long gap DOES rotate.
    real = _stamp("worker", clock, 20 * 60_000 + 1)
    assert real["sid"] != "s0"


def test_reconnection_within_the_window_keeps_the_same_session(_clean_identity_state):
    clock = _clean_identity_state
    _stamp("flash", clock, 0)
    soon = _stamp("flash", clock, 2 * 60_000)  # 2 min < 5 min ceiling
    assert soon["sid"] == "s0", "a reconnection after a brief gap cannot split the session in two"


# ── background noise NEVER fabricates a session by itself (2026-08-15) ─────────────────────────────────────
# Real finding while live-testing ⏻ (V2-092): `identity.end_session()` closes the session (`_session["id"]` to
# None) and right after emits ITS OWN "end" event — category `system`. With `session_id()` (which SELF-OPENS)
# as the source of `sid`, that same close event would reopen a NEW session in the act of closing the previous
# one — the master kept showing "EN CURSO" a second after finishing. The same happened with any ⏻ `run` event
# (stop/start/pausing/resumed) fired while the agent was already stopped. The session must stay CLOSED until
# REAL activity (not plumbing) reopens it.
def test_system_noise_does_not_resurrect_a_closed_session(monkeypatch):
    from observability import identity

    monkeypatch.setattr(identity, "_session", {"id": None, "started_ms": None, "source": ""})
    ev = {"kind": "run", "cat": "system"}
    observer.stamp_identity(ev)
    assert ev["sid"] == "", "a plumbing event can't reopen what just closed"
    assert identity._session["id"] is None, "and certainly must not leave a new session in its place"


def test_real_activity_still_opens_a_session_that_was_closed(monkeypatch):
    """The contrast: background noise opens nothing, but REAL activity still opens a new session on its own
    after a close — the original guarantee ("an event never goes without a session") is still alive where it
    matters."""
    from observability import identity

    monkeypatch.setattr(identity, "_session", {"id": None, "started_ms": None, "source": ""})
    ev = {"kind": "brain", "cat": "flash"}
    observer.stamp_identity(ev)
    assert ev["sid"], "real activity DOES have to open a session if none was open"
    assert identity._session["id"] == ev["sid"]
