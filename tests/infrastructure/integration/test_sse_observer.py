#
# test_sse_observer.py — voice/observer.py re-expresado sobre el bus (V2-001, T36). Verifica la BACK-COMPAT
# de `GET /events`: un evento emitido por observer.emit() llega IDÉNTICO a un suscriptor de observer.subscribe()
# (que ahora es una suscripción del bus al topic "observer"), incluida la entrega cross-loop del job-thread.
# Ejecutar: .venv/bin/pytest tests/infrastructure/integration/test_sse_observer.py
#
import asyncio
import threading

import pytest

import bus as busmod
from voice import observer


@pytest.fixture(autouse=True)
def _clean():
    busmod.reset()
    observer.clear_log()
    yield
    busmod.reset()


def test_emit_reaches_events_subscriber_identically():
    async def run():
        sub = observer.subscribe()                     # == GET /events
        ev = observer.emit("brain", "reply", text="hola", role="assistant")
        got = await asyncio.wait_for(sub.get(), timeout=1)
        return ev, got
    ev, got = asyncio.run(run())
    # el objeto entregado por SSE es EXACTAMENTE el ev que construyó observer.emit (mismos campos/valores)
    assert got is ev
    assert got["kind"] == "brain" and got["label"] == "reply"
    assert got["text"] == "hola" and got["role"] == "assistant"
    assert {"i", "t_ms", "rel_ms", "kind", "label", "text", "role"} <= set(got.keys())


def test_observer_is_a_bus_subscriber_on_topic_observer():
    async def run():
        raw = busmod.subscribe("observer")             # suscriptor crudo del bus al mismo topic
        observer.emit("transcript", "final", text="hi")
        return await asyncio.wait_for(raw.get(), timeout=1)
    ev = asyncio.run(run())
    assert ev["kind"] == "transcript" and ev["text"] == "hi"


def test_emit_from_worker_thread_crosses_to_events_loop():
    """La voz corre en el job-thread de LiveKit (otro loop). emit() desde ese hilo debe llegar al suscriptor
    de /events que vive en el loop de uvicorn — el bug histórico del put_nowait cross-loop, ahora resuelto."""
    async def run():
        sub = observer.subscribe()

        def worker():                                  # hilo sin loop asyncio = job-thread de LiveKit
            observer.emit("llm", "token", text="x")

        t = threading.Thread(target=worker)
        t.start(); t.join()
        return await asyncio.wait_for(sub.get(), timeout=1)
    ev = asyncio.run(run())
    assert ev["kind"] == "llm" and ev["label"] == "token"


def test_unsubscribe_stops_delivery():
    async def run():
        sub = observer.subscribe()
        observer.unsubscribe(sub)
        observer.emit("brain", "reply", text="y")
        await asyncio.sleep(0.01)
        return sub.queue.empty()
    assert asyncio.run(run()) is True


def test_emit_still_records_ring_and_returns_event():
    # el resto del contrato del observer (ring en memoria para /api/debug) sigue intacto
    observer.emit("error", "boom", text="oops")
    evs = observer.debug_events(kind="error")
    assert evs and evs[-1]["label"] == "boom"
