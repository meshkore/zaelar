"""Regression for a real bug (2026-08-16): a cluster peer-heartbeat trace fired after the operator stopped
the agent self-opened a brand-new "live" session — `stamp_identity`'s "background noise never fabricates a
session" guard (observer.py, 2026-08-15) only checks `cat in ("system", "pulse")`, and the root trace event of
a cluster-originated stimulus inherited `cat="flash"` from `kind="trace"`, independent of `origin="cluster"`.
`trace.begin()` now forces `cat="system"` for that one origin so the existing guard actually covers it.
"""
import bus as busmod
import pytest

from observability import identity
from voice import observer, trace


@pytest.fixture(autouse=True)
def _clean():
    busmod.reset()
    identity.end_session("test")
    observer.clear_log()
    yield
    busmod.reset()
    identity.end_session("test")
    observer.clear_log()


def test_cluster_origin_trace_is_classified_as_system_not_flash():
    tid = trace.begin("[cluster:commons · heartbeat] no reply for a while", origin="cluster")
    roots = [e for e in observer.debug_events(kind="trace") if e.get("trace") == tid]
    assert roots and roots[-1].get("cat") == "system"
    trace.adopt("")


def test_a_real_user_turn_still_gets_the_flash_family():
    """Contrast case: nothing about a normal turn's classification changed."""
    tid = trace.begin("qué tiempo hace", origin="turno")
    roots = [e for e in observer.debug_events(kind="trace") if e.get("trace") == tid]
    assert roots and roots[-1].get("cat") == "flash"
    trace.adopt("")


def test_cluster_heartbeat_after_stop_does_not_resurrect_a_session():
    """The actual reported symptom: with no session open (operator stopped the agent), a cluster heartbeat
    trace must NOT mint a new one — session_info() (read-only) stays empty."""
    assert identity.session_info().get("session_id") is None
    trace.begin("[cluster:commons · heartbeat] no reply for a while", origin="cluster")
    assert identity.session_info().get("session_id") is None, \
        "a cluster-origin event self-opened a session — exactly the bug this guards against"
    trace.adopt("")


def test_a_real_user_turn_after_stop_still_opens_a_session():
    """Contrast case: real user activity opening a session while stopped is unrelated behavior (governed by
    runstate, not identity) and must keep working."""
    assert identity.session_info().get("session_id") is None
    trace.begin("hola", origin="turno")
    assert identity.session_info().get("session_id") is not None
    trace.adopt("")
