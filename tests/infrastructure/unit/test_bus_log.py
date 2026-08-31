#
# test_log.py — durable log of bus events in SQLite (V2-001, T35). Verifies actual persistence to
# disk (temporary file via ZAELAR_DB), attachment as the bus sink, filters, and resilience.
#
# 2026-08-09: the sink became ASYNCHRONOUS (queues + writer thread). The bus calls it on the thread that PUBLISHES, which
# is often the voice thread, and a synchronous INSERT there was why the durable log had been disabled by default since V2-001.
# Therefore the tests now DRAIN before reading: `_write` no longer promises to have written, it promises
# not to have blocked.
# Run: .venv/bin/pytest tests/infrastructure/unit/test_bus_log.py
#
import asyncio
import importlib

import pytest

import bus as busmod


@pytest.fixture()
def log(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    from bus import log as logmod
    importlib.reload(logmod)   # rereads ZAELAR_DB and resets the module connection
    busmod.reset()
    yield logmod
    logmod.detach()
    logmod.close()
    busmod.reset()


def test_write_persists_and_reads_back(log):
    log._write({"topic": "brain.reply", "ts_ms": 1000.0, "payload": {"text": "hola"}})
    log._write({"topic": "widget.show", "ts_ms": 2000.0, "payload": {"id": "agenda"}})
    log.drain()
    assert log.count() == 2
    log.drain()
    rows = log.recent(10)
    assert rows[0]["topic"] == "widget.show"        # newest first
    assert rows[0]["payload"] == {"id": "agenda"}
    assert rows[1]["payload"] == {"text": "hola"}


def test_persists_across_connection_close(log, tmp_path):
    log._write({"topic": "memory.updated", "ts_ms": 1.0, "payload": {"n": 1}})
    log.close()                                     # simulates restart: new connection to the SAME file
    log.drain()
    assert log.count() == 1
    assert log.recent(1)[0]["payload"] == {"n": 1}


def test_attach_captures_bus_events(log):
    async def run():
        log.attach()
        await busmod.publish("memory.updated", {"id": 42})
        await busmod.publish("connector.msg", {"from": "wa"})
    asyncio.run(run())
    log.drain()
    assert log.count() == 2
    assert log.count("memory.updated") == 1


def test_topic_prefix_filter(log):
    log._write({"topic": "widget.show", "ts_ms": 1.0, "payload": 1})
    log._write({"topic": "widget.close", "ts_ms": 2.0, "payload": 2})
    log._write({"topic": "brain.reply", "ts_ms": 3.0, "payload": 3})
    log.drain()
    assert len(log.recent(10, topic="widget.*")) == 2
    assert len(log.recent(10, topic="brain.reply")) == 1


def test_non_serializable_payload_does_not_crash(log):
    class Weird:
        pass
    log._write({"topic": "x", "ts_ms": 1.0, "payload": Weird()})
    log.drain()
    assert log.count() == 1           # stored as str, does not crash
    assert log.recent(1)[0]["topic"] == "x"


def test_attach_is_idempotent(log):
    async def run():
        log.attach()
        log.attach()                  # second time = no-op, does not duplicate the sink
        await busmod.publish("memory.updated", {})
    asyncio.run(run())
    log.drain()
    assert log.count() == 1


def test_the_sink_never_blocks_the_publisher(log):
    """The new CONTRACT: `_write` queues and returns. This allows the durable log to remain enabled without an
    INSERT per event interfering with the voice thread (the reason it had been disabled since V2-001).

    2026-08-20: it measured an ABSOLUTE THRESHOLD (`< 200 ms`), making it fail because of the MACHINE rather than the code —
    exactly what `test_suite_isolation.py` exists to prevent. Queuing 2000 events takes ~2 ms when measured
    in isolation, so the ceiling had 100x of headroom… and even so it reached 206 ms when running the entire suite,
    with everything in one process. The number was not poorly chosen: the TEST'S FORM was poorly chosen.

    It now measures the PROPERTY, which is relative and therefore immune to load: queuing must be
    dramatically cheaper than the write it replaces, and both experience the same machine at the same
    moment. The absolute ceiling remains only as a very generous safety net: if someone makes the sink
    synchronous again, queuing and writing become the SAME operation and the ratio approaches 1.
    """
    import time

    # 2026-08-21, SECOND recurrence: the relative ratio fixed dependence on the MACHINE MODEL, but not
    # dependence on the INSTANT. With the entire suite in one process —that night it grew from 3,284 to 3,923 tests— a single
    # scheduler preemption during the ~2 ms of queuing is enough to sink the ratio, and the test fails
    # because of the clock rather than the code. A time measurement taken ONCE measures the machine; taken several times and
    # keeping the BEST, it measures the path. The property remains unattainable for a synchronous sink: there,
    # queuing and writing are the SAME operation, so the ratio approaches 1 in all three rounds.
    mejor, escritos, encolar = 0.0, 0, 0.0
    for _ in range(3):
        t0 = time.perf_counter()
        for i in range(2000):
            log._write({"topic": "x", "ts_ms": float(i), "payload": {"i": i}})
        encolar = time.perf_counter() - t0
        t1 = time.perf_counter()
        log.drain(timeout=10.0)
        escribir = time.perf_counter() - t1
        escritos += 2000
        assert log.count() == escritos, "encolar rápido no vale de nada si los eventos no acaban en la tabla"
        mejor = max(mejor, (escribir / encolar) if encolar > 0 else float("inf"))
        if mejor >= 5:
            break
    # Measured on this machine: queuing ~2 ms, writing ~116 ms (58x). 5x is required — leaving a factor of 10 of headroom.
    assert mejor >= 5, (
        f"la mejor de 3 rondas dio escribir/encolar = {mejor:.1f}x — encolar ya no es dramáticamente más barato "
        f"que escribir, así que `_write` está pagando el INSERT en el hilo que publica (que muchas veces es el "
        f"de la voz)")
    assert encolar < 2.0, f"encolar 2000 eventos tardó {encolar:.1f}s — eso no es «no bloquea» en ninguna máquina"


def test_retention_caps_the_table(log, monkeypatch):
    """The other reason it had been disabled: unbounded growth. There is now a row ceiling and age-based pruning."""
    monkeypatch.setattr(log, "_MAX_ROWS", 10)
    monkeypatch.setattr(log, "_RETENTION_DAYS", 0)      # isolate the row ceiling from age-based pruning
    for i in range(25):
        log._write({"topic": "x", "ts_ms": float(i), "payload": {"i": i}})
    log.drain(timeout=5.0)
    log.prune()
    assert log.count() == 10, "the ceiling must leave exactly the N most recent"
    assert log.recent(1)[0]["payload"]["i"] == 24, "and the ones left are the LAST, not the first"


def test_a_full_queue_drops_log_instead_of_slowing_the_caller(log, monkeypatch):
    """Under saturation, LOG is lost, never speed: voice has priority. And discards are COUNTED, so that
    a gap in the data is visible rather than silent."""
    import queue as _q
    monkeypatch.setattr(log, "_q", _q.Queue(maxsize=2))
    log._dropped["n"] = 0
    for i in range(10):
        log._write({"topic": "x", "ts_ms": float(i), "payload": {"i": i}})
    assert log._dropped["n"] > 0
    assert log.stats()["dropped"] == log._dropped["n"]


def test_the_heartbeat_is_not_persisted(log):
    """The loop ticks at ~1 Hz: persisting the heartbeat would be ~140,000 rows per day of an event WITHOUT data, which would
    consume retention and drown out what actually matters. It still reaches the live UI via SSE."""
    log._write({"topic": "loop.tick", "ts_ms": 1.0, "payload": {"n": 1}})
    log._write({"topic": "observer", "ts_ms": 2.0, "payload": {"kind": "pulse", "label": "tick"}})
    log._write({"topic": "observer", "ts_ms": 3.0, "payload": {"kind": "brain", "label": "decide"}})
    log.drain()
    assert log.count() == 1, "only the event with real content should remain"
    assert log.recent(1)[0]["payload"]["kind"] == "brain"
