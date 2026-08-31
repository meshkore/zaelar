"""Tests for voice/trace.py (V2-044) — trace propagation through the system's real asyncio paths."""
import asyncio

from voice import trace


def test_begin_sets_current_and_emits_root():
    tid = trace.begin("hola, pon música", origin="turno")
    assert tid.startswith("T") and "·" in tid
    assert trace.current() == tid
    # the root event ended up in the observer's ring
    from voice import observer
    roots = [e for e in observer.debug_events(kind="trace") if e.get("trace") == tid]
    assert roots and roots[-1].get("root") is True and roots[-1].get("origin") == "turno"
    trace.adopt("")


def test_emit_attaches_trace_and_span():
    from voice import observer
    tid = trace.begin("prueba emit", origin="probe")
    ev = observer.emit("brain", "unit-test", text="x")
    assert ev.get("trace") == tid
    trace.adopt(tid, span="rail:test")
    ev2 = observer.emit("brain", "unit-test-span", text="y")
    assert ev2.get("trace") == tid and ev2.get("span") == "rail:test"
    # the caller can force the explicit trace (cross-loop seams)
    ev3 = observer.emit("brain", "unit-test-explicit", extra={"trace": "T0·beef"})
    assert ev3.get("trace") == "T0·beef"
    trace.adopt("")


def test_propagates_through_create_task_and_to_thread():
    async def main():
        tid = trace.begin("propagación", origin="probe")

        async def child():
            return trace.current()

        got_task = await asyncio.create_task(child())        # create_task copies the context
        got_thread = await asyncio.to_thread(trace.current)  # to_thread copies the context
        return tid, got_task, got_thread

    tid, got_task, got_thread = asyncio.run(main())
    assert got_task == tid
    assert got_thread == tid


def test_scope_restores_previous():
    trace.adopt("T9·aaaa", span="worker:9")
    with trace.scope("T8·bbbb", span="memoria"):
        assert trace.current() == "T8·bbbb"
        assert trace.current_span() == "memoria"
    assert trace.current() == "T9·aaaa"
    assert trace.current_span() == "worker:9"
    trace.adopt("")


def test_no_trace_no_field():
    from voice import observer
    trace.adopt("")
    ev = observer.emit("brain", "sin-traza")
    assert "trace" not in ev


# ── active() — the trace for readers that CANNOT inherit the ContextVar (2026-08-16) ────────────────────────────
# Real-source audit: the handlers in `voice/engine/pipeline/agent.py` (state, VAD, TTS/STT metrics, the
# zaelar transcript) run in SIBLING tasks of the one that sets the turn's trace — they never see it through the
# ContextVar, regardless of the actual temporal order (confirmed against livekit-agents 1.6.6). `active()` is the
# explicit pointer that fixes precisely that.
def test_active_reflects_the_most_recently_begun_trace():
    tid = trace.begin("hola", origin="turno")
    assert trace.active() == tid
    trace.adopt("")


def test_active_reflects_an_adopted_trace_too():
    trace.begin("x", origin="turno")
    trace.adopt("T5·zzzz", span="worker:1")
    assert trace.active() == "T5·zzzz"
    trace.adopt("")


def test_a_kickoff_becomes_the_sessions_general_fallback():
    tid = trace.begin("motor arrancado", origin="kickoff")
    trace.adopt("")   # the ContextVar is cleared (end of the kickoff turn)…
    assert trace.current() == ""
    assert trace.active() == tid, "…but active() keeps pointing to the kickoff until something more recent appears"


def test_active_expires_and_falls_back_to_general_not_a_stale_turn():
    """An event arriving long after the last trace was set cannot attach itself to a turn that
probably already closed — it would reopen a "closed" flow in the master with phantom activity."""
    kickoff = trace.begin("motor arrancado", origin="kickoff")
    tid = trace.begin("hola", origin="turno")
    assert trace.active() == tid
    trace._active_at -= 10   # simulates that 10s passed since that begin(), without actually sleeping
    assert trace.active() == kickoff
    assert trace.active(max_age_s=60) == tid, "the margin is configurable — with a wider one it remains valid"


# ── merge() — two traces turn out to be the SAME task (2026-08-16) ────────────────────────────────────────────────
# "By the second or third sentence we realize that the two turns are the same... I would leave that feature
# available" — the operator requested the CAPABILITY to merge two flows, with the OLDEST always as the titular.
def test_merge_keeps_the_older_trace_as_titular_regardless_of_argument_order():
    assert trace.merge("T5·aaaa", "T9·bbbb") == "T5·aaaa"
    assert trace.merge("T9·bbbb", "T5·aaaa") == "T5·aaaa", "the order of the arguments must not matter"


def test_merge_emits_a_marker_stamped_on_the_newer_trace_not_ambient():
    from voice import observer
    tid = trace.merge("T5·aaaa", "T9·bbbb")
    assert tid == "T5·aaaa"
    markers = [e for e in observer.debug_events(kind="trace")
               if e.get("label") == "merge" and e.get("trace") == "T9·bbbb"]
    assert markers, "the marker must appear under the ID being merged, not under the titular"
    assert markers[-1].get("merge_into") == "T5·aaaa"


def test_merge_with_itself_or_empty_is_a_safe_noop():
    assert trace.merge("T5·aaaa", "T5·aaaa") == "T5·aaaa"
    assert trace.merge("", "T5·aaaa") == "T5·aaaa"
    assert trace.merge("T5·aaaa", "") == "T5·aaaa"
    assert trace.merge("", "") == ""


def test_cluster_and_pulso_origins_never_touch_active():
    """The MeshKore bridge (connectors/meshkore/bridge.py) runs in the SAME process and also calls begin() — if
it touched active(), a cluster tick would attach its events to the VOICE pipeline (VAD/TTS/state) of the trace of
a cluster conversation that has nothing to do with it."""
    tid = trace.begin("hola", origin="turno")
    trace.begin("[cluster:x] evento", origin="cluster")
    trace.begin("[cluster:x] heartbeat", origin="pulso")
    assert trace.active() == tid
    trace.adopt("")
