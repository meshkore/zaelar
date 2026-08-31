"""Tests for nucleo/loop.py (V2-005 · T70/T74/T76) — the heartbeat: fires overdue items, sparks, consolidates, emits to the bus."""
import asyncio
import time

import pytest

import bus
from memory import db as memdb
from nucleo import loop as nloop
from nucleo import scheduler, sparks


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    bus.reset()
    yield
    memdb.reset_db()
    bus.reset()


def _never_spark():
    # Gate that NEVER permits a spark (isolates the firing/consolidation tests).
    return sparks.SparkGate(daily_max=0, min_gap_s=0, prob=0.0, clock=lambda: 0.0, rng=lambda: 1.0)


def test_tick_does_not_deliver_before_due(fresh_db, monkeypatch):
    delivered = []

    async def deliver(title, text):
        delivered.append((title, text))

    base = 1000.0
    scheduler.create("recuérdame estirar", "10m", name="estirar", now=base)
    lp = nloop.OrchestratorLoop(spark_gate=_never_spark(), deliver=deliver, consolidate_every_s=1e9)

    monkeypatch.setattr(nloop.time, "time", lambda: base + 60)   # not due yet
    asyncio.run(lp.tick())
    assert delivered == []


def test_fire_due_via_tick_with_patched_clock(fresh_db, monkeypatch):
    delivered = []

    async def deliver(title, text):
        delivered.append((title, text))

    base = 1000.0
    scheduler.create("bebe agua", "10m", name="agua", now=base)
    lp = nloop.OrchestratorLoop(spark_gate=_never_spark(), deliver=deliver, consolidate_every_s=1e9)

    # Advance the loop module's clock past the due time.
    monkeypatch.setattr(nloop.time, "time", lambda: base + 601)
    asyncio.run(lp.tick())
    assert len(delivered) == 1 and delivered[0] == ("agua", "bebe agua")
    # The "once" task is no longer due.
    assert scheduler.due(now=base + 100000) == []


def test_tick_emits_loop_tick_on_bus(fresh_db):
    lp = nloop.OrchestratorLoop(spark_gate=_never_spark(), deliver=_noop, consolidate_every_s=1e9)
    seen = []
    sub = bus.subscribe("loop.*")

    async def run():
        await lp.tick()
        # Drain whatever is available (best effort, without blocking).
        try:
            ev = await asyncio.wait_for(sub.get(), timeout=0.5)
            seen.append(ev)
        except asyncio.TimeoutError:
            pass

    asyncio.run(run())
    sub.close()
    assert seen  # al menos loop.tick


def test_consolidation_triggers_off_hot_path(fresh_db, monkeypatch):
    calls = []
    from memory import api as memapi

    # **kwargs, and not cosmetically: since the 2026-08-23 audit, the loop INJECTS the ledger cleanup for
    # workers (`prune_workers_fn`) instead of memory importing `nucleo.workers`. A fixed-arity stub
    # blows up with TypeError… which `_maybe_consolidate`'s `except Exception` turns into a warning, so
    # the symptom is not an error but that the entire consolidation SILENTLY STOPS RUNNING. Capture the hook
    # to require that the injection really arrives: without it, this test would pass with the loop calling directly.
    def _fake(**kw):
        calls.append(kw)
        return {"deduped": 0, "evicted": 0, "promoted": 0}

    monkeypatch.setattr(memapi, "consolidate", _fake)

    lp = nloop.OrchestratorLoop(spark_gate=_never_spark(), deliver=_noop, consolidate_every_s=0)
    lp._last_consolidate = 0.0

    async def run():
        await lp.tick()

    asyncio.run(run())
    assert len(calls) == 1, "consolidation must fire once per overdue cycle"
    assert callable(calls[0].get("prune_workers_fn")), (
        "the loop stopped injecting the ledger cleanup: memory has not done it on its own since 2026-08-23, "
        "so the Brain Workers ledger would grow without limit and nothing would fail")


def test_spark_fires_when_gate_allows(fresh_db, monkeypatch):
    delivered = []

    async def deliver(title, text):
        delivered.append((title, text))

    monkeypatch.setattr(sparks, "propose", lambda now=None: "un pensamiento suelto")
    gate = sparks.SparkGate(daily_max=5, min_gap_s=0, prob=1.0, clock=lambda: 0.0, rng=lambda: 0.0)
    lp = nloop.OrchestratorLoop(spark_gate=gate, deliver=deliver, consolidate_every_s=1e9)

    asyncio.run(lp.tick())
    assert delivered == [("zaelar", "un pensamiento suelto")]


def test_spark_discarded_when_nothing_useful(fresh_db, monkeypatch):
    delivered = []

    async def deliver(title, text):
        delivered.append((title, text))

    monkeypatch.setattr(sparks, "propose", lambda now=None: None)   # usefulness gate: nothing to contribute
    gate = sparks.SparkGate(daily_max=5, min_gap_s=0, prob=1.0, clock=lambda: 0.0, rng=lambda: 0.0)
    lp = nloop.OrchestratorLoop(spark_gate=gate, deliver=deliver, consolidate_every_s=1e9)

    asyncio.run(lp.tick())
    assert delivered == []


async def _noop(title, text):
    return None


# ── expired confirmations get told to the operator, over the same proactive rails (2026-08-16) ────────────
def test_tick_delivers_an_expired_confirmations_notice(fresh_db, monkeypatch):
    """Real incident: a confirmation nobody ever answered (superseded, or plain silence past the 90s TTL) used
    to just vanish — the task stayed undone with zero signal. `widgets/confirm.py::_sweep()` already closes its
    flow synchronously; the loop's job is the other half, telling the operator, exactly like a stuck/timed-out
    worker gets a heads-up."""
    from widgets import confirm

    delivered = []

    async def deliver(title, text):
        delivered.append((title, text))

    confirm.reset()
    confirm._EXPIRED_QUEUE.clear()
    confirm._EXPIRED_QUEUE.append({"widget_id": "agenda", "question": "¿Vacío la agenda entera?"})

    lp = nloop.OrchestratorLoop(spark_gate=_never_spark(), deliver=deliver, consolidate_every_s=1e9)
    asyncio.run(lp.tick())

    assert len(delivered) == 1
    title, text = delivered[0]
    assert title == "zaelar"
    assert "¿Vacío la agenda entera?" in text
    assert confirm.drain_expired_notices() == [], "the loop must drain the queue, not leave it for the next tick"


def test_tick_says_nothing_when_no_confirmation_expired(fresh_db):
    from widgets import confirm

    confirm.reset()
    confirm._EXPIRED_QUEUE.clear()

    delivered = []

    async def deliver(title, text):
        delivered.append((title, text))

    lp = nloop.OrchestratorLoop(spark_gate=_never_spark(), deliver=deliver, consolidate_every_s=1e9)
    asyncio.run(lp.tick())

    assert delivered == []


# ── _supervise_stale_flows (2026-08-16) — a conversational flow the operator walked away from ─────────────────
# Real incident: the master kept showing several "en curso" flows from a session the operator had abandoned
# minutes earlier. `_maybe_close_flow` (voice/engine/llm/providers/nucleo.py) only gets ONE chance to close a
# flow, at the exact moment its own turn finishes — if it correctly deferred back then, nothing ever revisits
# that decision once the deferring condition clears on its own. This is that revisit, on a slow timer.
@pytest.fixture
def flow_session(fresh_db):
    """One open observability session with the bus's SQLite sink WIRED (`_supervise_stale_flows` reads
    `observability.flows.flows()`, which queries the PERSISTED table — the in-memory ring `observer.emit()`
    always fills is not enough here, unlike most other tests in this suite). Same fixture shape as
    `tests/infrastructure/unit/core/test_observability_flows.py::wired`."""
    import bus
    from bus import log as _log
    from observability import identity
    from voice import observer, trace

    _log._conn = None
    _log.detach(bus)
    _log.attach(bus)
    identity.end_session("test")
    observer.clear_log()
    trace.adopt("")
    sid = identity.session_id()   # self-opens
    yield sid
    identity.end_session("test")
    observer.clear_log()
    trace.adopt("")
    _log.detach(bus)
    _log._conn = None


def _make_stale_flow(text: str) -> str:
    import time as _t
    from voice import trace
    tid = trace.begin(text, origin="turno")
    trace.adopt("")
    _t.sleep(0.25)   # let the bus's background writer thread persist the root event before flows() queries it
    return tid


def test_stale_flow_with_no_worker_and_no_pending_confirm_gets_closed(flow_session):
    from voice import observer

    tid = _make_stale_flow("necesito que cierres todos los widgets")
    lp = nloop.OrchestratorLoop(spark_gate=_never_spark(), deliver=_noop, consolidate_every_s=1e9)
    future = time.time() + lp._stale_flow_secs + 1
    asyncio.run(lp._supervise_stale_flows(future))

    closes = [e for e in observer.debug_events(kind="flow") if e.get("trace") == tid]
    assert closes and closes[-1].get("reason") == "stale_no_input"


def test_a_recent_flow_within_the_grace_window_is_left_alone(flow_session):
    from voice import observer

    tid = _make_stale_flow("dame un segundo que lo pienso")
    lp = nloop.OrchestratorLoop(spark_gate=_never_spark(), deliver=_noop, consolidate_every_s=1e9)
    asyncio.run(lp._supervise_stale_flows(time.time() + 5))   # well under the 900s default

    assert not [e for e in observer.debug_events(kind="flow") if e.get("trace") == tid]


def test_a_stale_flow_with_a_live_worker_never_closes_no_matter_how_old(flow_session, monkeypatch):
    """Operator's invariant, verbatim: "if it is an active search keeping a Brain Worker running, it must
    NEVER be closed until it is finished — the ball is in the people's court." """
    from nucleo import dispatch
    from voice import observer

    tid = _make_stale_flow("búscame un hotel para dentro de dos semanas")
    monkeypatch.setattr(dispatch, "has_live_trace", lambda t: t == tid)
    lp = nloop.OrchestratorLoop(spark_gate=_never_spark(), deliver=_noop, consolidate_every_s=1e9)
    asyncio.run(lp._supervise_stale_flows(time.time() + 100_000))   # arbitrarily old — still must not close

    assert not [e for e in observer.debug_events(kind="flow") if e.get("trace") == tid]


def test_a_stale_flow_with_a_pending_confirmation_is_left_for_the_operators_answer(flow_session):
    from widgets import confirm
    from voice import observer

    tid = _make_stale_flow("borra todos los datos de mi agenda")
    confirm.reset()
    confirm._PENDING["agenda"] = {"action": "data", "question": "¿seguro?", "op": None,
                                   "ts": time.time(), "trace_id": tid}
    try:
        lp = nloop.OrchestratorLoop(spark_gate=_never_spark(), deliver=_noop, consolidate_every_s=1e9)
        asyncio.run(lp._supervise_stale_flows(time.time() + lp._stale_flow_secs + 1))
        assert not [e for e in observer.debug_events(kind="flow") if e.get("trace") == tid]
    finally:
        confirm.reset()


def test_supervise_stale_flows_is_throttled_and_does_not_run_every_tick(flow_session):
    """A real SQL query, not RAM bookkeeping — must not run on every 1Hz pulse."""
    from voice import observer

    tid = _make_stale_flow("necesito que cierres todos los widgets")
    lp = nloop.OrchestratorLoop(spark_gate=_never_spark(), deliver=_noop, consolidate_every_s=1e9)
    future = time.time() + lp._stale_flow_secs + 1
    asyncio.run(lp._supervise_stale_flows(future))       # first call: runs
    asyncio.run(lp._supervise_stale_flows(future + 1))   # immediately again: throttled, no duplicate close

    closes = [e for e in observer.debug_events(kind="flow") if e.get("trace") == tid]
    assert len(closes) == 1
