#
# test_bus.py — el Sistema Nervioso in-process (V2-001). Cubre: pub/sub con wildcards, aislamiento por
# patrón, entrega cross-loop de emit_sync (job-thread de LiveKit → loop de uvicorn), y los sinks síncronos.
# Estilo del repo: tests SÍNCRONOS que envuelven lo async con asyncio.run (sin dependencia pytest-asyncio).
# Ejecutar: .venv/bin/pytest tests/infrastructure/unit/test_bus.py
#
import asyncio
import threading

import pytest

import bus as busmod
from bus import Bus


@pytest.fixture(autouse=True)
def _clean():
    busmod.reset()
    yield
    busmod.reset()


def test_publish_reaches_matching_subscriber():
    async def run():
        sub = busmod.subscribe("brain.reply")
        await busmod.publish("brain.reply", {"text": "hola"})
        return await asyncio.wait_for(sub.get(), timeout=1)
    assert asyncio.run(run()) == {"text": "hola"}


def test_wildcard_pattern():
    async def run():
        sub = busmod.subscribe("widget.*")
        await busmod.publish("widget.show", {"id": "agenda"})
        await busmod.publish("brain.reply", {"text": "x"})   # no debe llegar
        ev = await asyncio.wait_for(sub.get(), timeout=1)
        return ev, sub.queue.empty()
    ev, empty = asyncio.run(run())
    assert ev == {"id": "agenda"} and empty


def test_star_receives_everything():
    async def run():
        sub = busmod.subscribe("*")
        await busmod.publish("a.b", 1)
        await busmod.publish("c.d", 2)
        return (await asyncio.wait_for(sub.get(), 1), await asyncio.wait_for(sub.get(), 1))
    assert asyncio.run(run()) == (1, 2)


def test_non_matching_subscriber_gets_nothing():
    async def run():
        sub = busmod.subscribe("memory.updated")
        await busmod.publish("loop.tick", {})
        await asyncio.sleep(0.01)
        return sub.queue.empty()
    assert asyncio.run(run()) is True


def test_unsubscribe_stops_delivery():
    async def run():
        sub = busmod.subscribe("brain.*")
        busmod.unsubscribe(sub)
        await busmod.publish("brain.reply", {"text": "y"})
        await asyncio.sleep(0.01)
        return sub.queue.empty()
    assert asyncio.run(run()) is True


def test_async_iteration():
    async def run():
        sub = busmod.subscribe("loop.tick")
        got = []

        async def consume():
            async for ev in sub:
                got.append(ev)
                if len(got) == 2:
                    break

        task = asyncio.create_task(consume())
        await asyncio.sleep(0)
        await busmod.publish("loop.tick", 1)
        await busmod.publish("loop.tick", 2)
        await asyncio.wait_for(task, timeout=1)
        return got
    assert asyncio.run(run()) == [1, 2]


def test_emit_sync_cross_loop_delivery():
    """El caso de producción: la voz corre en el job-thread de LiveKit (OTRO loop) y publica al bus; el
    suscriptor vive en el loop de uvicorn. emit_sync debe cruzar de forma segura (call_soon_threadsafe)."""
    async def run():
        sub = busmod.subscribe("observer")           # creado en ESTE loop

        def worker():
            # otro hilo, SIN loop asyncio corriendo: exactamente el job-thread de LiveKit
            busmod.emit_sync("observer", {"kind": "llm", "label": "token"})

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        return await asyncio.wait_for(sub.get(), timeout=1)
    assert asyncio.run(run()) == {"kind": "llm", "label": "token"}


def test_sink_receives_envelope_with_metadata():
    async def run():
        seen = []
        busmod.add_sink(lambda rec: seen.append(rec))
        await busmod.publish("memory.updated", {"id": 7})
        return seen
    seen = asyncio.run(run())
    assert len(seen) == 1
    rec = seen[0]
    assert rec["topic"] == "memory.updated"
    assert rec["payload"] == {"id": 7}
    assert isinstance(rec["ts_ms"], float)


def test_sink_exception_does_not_break_dispatch():
    async def run():
        def bad(_rec):
            raise RuntimeError("boom")
        busmod.add_sink(bad)
        sub = busmod.subscribe("x.*")
        await busmod.publish("x.y", 1)             # el sink revienta pero la entrega debe seguir
        return await asyncio.wait_for(sub.get(), timeout=1)
    assert asyncio.run(run()) == 1


def test_isolated_bus_instances_do_not_cross_talk():
    a, b = Bus(), Bus()
    sa = a.subscribe("*")
    a.emit_sync("t", 1)
    b.emit_sync("t", 2)
    assert sa.queue.get_nowait() == 1
    assert sa.queue.empty()
