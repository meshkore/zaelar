"""Tests de voice/trace.py (V2-044) — propagación del trace por los caminos asyncio reales del sistema."""
import asyncio

from voice import trace


def test_begin_sets_current_and_emits_root():
    tid = trace.begin("hola, pon música", origin="turno")
    assert tid.startswith("T") and "·" in tid
    assert trace.current() == tid
    # el evento raíz quedó en el anillo del observador
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
    # el caller puede forzar el trace explícito (costuras cross-loop)
    ev3 = observer.emit("brain", "unit-test-explicit", extra={"trace": "T0·beef"})
    assert ev3.get("trace") == "T0·beef"
    trace.adopt("")


def test_propagates_through_create_task_and_to_thread():
    async def main():
        tid = trace.begin("propagación", origin="probe")

        async def child():
            return trace.current()

        got_task = await asyncio.create_task(child())        # create_task copia el contexto
        got_thread = await asyncio.to_thread(trace.current)  # to_thread copia el contexto
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
