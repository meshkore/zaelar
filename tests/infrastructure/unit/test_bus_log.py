#
# test_log.py — log durable de eventos del bus en SQLite (V2-001, T35). Verifica persistencia real a
# disco (fichero temporal vía ZAELAR_DB), enganche como sink del bus, filtros y resiliencia.
# Ejecutar: .venv/bin/pytest tests/infrastructure/unit/test_bus_log.py
#
import asyncio
import importlib

import pytest

import bus as busmod


@pytest.fixture()
def log(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    from bus import log as logmod
    importlib.reload(logmod)   # re-lee ZAELAR_DB y resetea la conexión de módulo
    busmod.reset()
    yield logmod
    logmod.detach()
    logmod.close()
    busmod.reset()


def test_write_persists_and_reads_back(log):
    log._write({"topic": "brain.reply", "ts_ms": 1000.0, "payload": {"text": "hola"}})
    log._write({"topic": "widget.show", "ts_ms": 2000.0, "payload": {"id": "agenda"}})
    assert log.count() == 2
    rows = log.recent(10)
    assert rows[0]["topic"] == "widget.show"        # más nuevo primero
    assert rows[0]["payload"] == {"id": "agenda"}
    assert rows[1]["payload"] == {"text": "hola"}


def test_persists_across_connection_close(log, tmp_path):
    log._write({"topic": "loop.tick", "ts_ms": 1.0, "payload": {"n": 1}})
    log.close()                                     # simula reinicio: nueva conexión al MISMO fichero
    assert log.count() == 1
    assert log.recent(1)[0]["payload"] == {"n": 1}


def test_attach_captures_bus_events(log):
    async def run():
        log.attach()
        await busmod.publish("memory.updated", {"id": 42})
        await busmod.publish("connector.msg", {"from": "wa"})
    asyncio.run(run())
    assert log.count() == 2
    assert log.count("memory.updated") == 1


def test_topic_prefix_filter(log):
    log._write({"topic": "widget.show", "ts_ms": 1.0, "payload": 1})
    log._write({"topic": "widget.close", "ts_ms": 2.0, "payload": 2})
    log._write({"topic": "brain.reply", "ts_ms": 3.0, "payload": 3})
    assert len(log.recent(10, topic="widget.*")) == 2
    assert len(log.recent(10, topic="brain.reply")) == 1


def test_non_serializable_payload_does_not_crash(log):
    class Weird:
        pass
    log._write({"topic": "x", "ts_ms": 1.0, "payload": Weird()})
    assert log.count() == 1           # se guarda como str, no revienta
    assert log.recent(1)[0]["topic"] == "x"


def test_attach_is_idempotent(log):
    async def run():
        log.attach()
        log.attach()                  # segunda vez = no-op, no duplica el sink
        await busmod.publish("loop.tick", {})
    asyncio.run(run())
    assert log.count() == 1
