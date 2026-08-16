"""Tests de nucleo/loop.py (V2-005 · T70/T74/T76) — el latido: dispara vencidos, chispas, consolida, emite bus."""
import asyncio

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
    # gate que NUNCA permite chispa (aísla los tests de disparo/consolidación)
    return sparks.SparkGate(daily_max=0, min_gap_s=0, prob=0.0, clock=lambda: 0.0, rng=lambda: 1.0)


def test_tick_does_not_deliver_before_due(fresh_db, monkeypatch):
    delivered = []

    async def deliver(title, text):
        delivered.append((title, text))

    base = 1000.0
    scheduler.create("recuérdame estirar", "10m", name="estirar", now=base)
    lp = nloop.OrchestratorLoop(spark_gate=_never_spark(), deliver=deliver, consolidate_every_s=1e9)

    monkeypatch.setattr(nloop.time, "time", lambda: base + 60)   # aún no vence
    asyncio.run(lp.tick())
    assert delivered == []


def test_fire_due_via_tick_with_patched_clock(fresh_db, monkeypatch):
    delivered = []

    async def deliver(title, text):
        delivered.append((title, text))

    base = 1000.0
    scheduler.create("bebe agua", "10m", name="agua", now=base)
    lp = nloop.OrchestratorLoop(spark_gate=_never_spark(), deliver=deliver, consolidate_every_s=1e9)

    # avanza el reloj del módulo loop más allá del vencimiento
    monkeypatch.setattr(nloop.time, "time", lambda: base + 601)
    asyncio.run(lp.tick())
    assert len(delivered) == 1 and delivered[0] == ("agua", "bebe agua")
    # la tarea "una vez" ya no vence
    assert scheduler.due(now=base + 100000) == []


def test_tick_emits_loop_tick_on_bus(fresh_db):
    lp = nloop.OrchestratorLoop(spark_gate=_never_spark(), deliver=_noop, consolidate_every_s=1e9)
    seen = []
    sub = bus.subscribe("loop.*")

    async def run():
        await lp.tick()
        # drena lo que haya (best-effort, sin bloquear)
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
    monkeypatch.setattr(memapi, "consolidate", lambda: calls.append(1) or {"deduped": 0, "evicted": 0, "promoted": 0})

    lp = nloop.OrchestratorLoop(spark_gate=_never_spark(), deliver=_noop, consolidate_every_s=0)
    lp._last_consolidate = 0.0

    async def run():
        await lp.tick()

    asyncio.run(run())
    assert calls == [1]


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

    monkeypatch.setattr(sparks, "propose", lambda now=None: None)   # gate de utilidad: nada que aportar
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
