"""Regression for a real bug (2026-08-16): a cluster peer-heartbeat trace fired after the operator stopped
the agent self-opened a brand-new "live" session — `stamp_identity`'s "background noise never fabricates a
session" guard (observer.py, 2026-08-15) only checks `cat in ("system", "pulse")`, and the root trace event of
a cluster-originated stimulus inherited `cat="flash"` from `kind="trace"`, independent of `origin="cluster"`.
`trace.begin()` now forces `cat="system"` for that one origin so the existing guard actually covers it.

Second, broader finding the SAME day: the `cat` check alone wasn't enough. Reloading the browser tab with the
agent globally STOPPED (`runstate.stopped()`) fired ordinary `widget`/`ui` state transitions (cat="widget"),
and THOSE self-opened a fresh session too — reappearing in the backoffice master as "EN CURSO" instantly on
page refresh, even with the ⏻ badge correctly showing "off" right next to it. `stamp_identity()` now also
checks `runstate.stopped()`, independent of category.
"""
import bus as busmod
import pytest

from memory import db as memdb
from observability import identity
from nucleo import runstate
from voice import observer, trace


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    # NOTE: does not reset `runstate` on the way IN — the root conftest's own autouse fixture already forces
    # RUNNING before every test (reading the operator's real DB here would leak whatever ⏻ state their actual
    # install happens to be in). It IS reset on the way OUT, so a test that stops the agent doesn't leak that
    # into whichever test runs next.
    #
    # ZAELAR_DB (2026-08-31): the note above worried about READING the operator's database and missed the far
    # worse half — two tests here drive `runstate.stop("operator")` for real, and `_persist` WRITES the switch to
    # `sys_kv`. `_reset_for_tests()` on the way out clears only the in-process cache, so the row stayed STOPPED
    # and the operator's next engine restart obeyed it: running this suite quietly turned his agent off, with
    # `src="operator"` so it did not even look like a test had done it. A unit test never touches a live artefact.
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    busmod.reset()
    identity.end_session("test")
    observer.clear_log()
    yield
    busmod.reset()
    identity.end_session("test")
    observer.clear_log()
    runstate._reset_for_tests()
    memdb.reset_db()


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


def test_a_real_user_turn_still_opens_a_session_while_running():
    """Contrast case: with the agent genuinely running (the default, and the only state this fixture leaves
    `runstate` in), real user activity opening a session is unaffected."""
    assert runstate.stopped() is False
    assert identity.session_info().get("session_id") is None
    trace.begin("hola", origin="turno")
    assert identity.session_info().get("session_id") is not None
    trace.adopt("")


def test_a_widget_ui_event_after_a_real_stop_does_not_open_a_session():
    """The actual reported symptom (2026-08-16): the operator saw the ⏻ badge correctly say "off" in the
    master, and the session list STILL showed "EN CURSO" the instant they reloaded the local agent's page —
    an ordinary `widget`/`ui` event (cat="widget", nothing to do with cluster/trace) self-opened a new one."""
    import asyncio
    asyncio.run(runstate.stop("operator"))
    assert runstate.stopped() is True
    assert identity.session_info().get("session_id") is None

    ev = observer.emit("ui", "agent:state", extra={"state": "starting", "prev": "none"})
    assert ev.get("cat") == "widget", "sanity: this is NOT a system/pulse event — the old guard would miss it"
    assert not ev.get("sid"), "a widget/ui event while genuinely stopped must not mint a session"
    assert identity.session_info().get("session_id") is None


def test_a_real_user_turn_does_not_open_a_session_while_stopped():
    """Same invariant from the other direction: even a `turno`-origin trace (which normally SHOULD open a
    session) must not, while the agent is stopped — "parar es parar" has no exception for "but it looked
    like a real turn"."""
    import asyncio
    asyncio.run(runstate.stop("operator"))
    trace.begin("hola", origin="turno")
    assert identity.session_info().get("session_id") is None
    trace.adopt("")
