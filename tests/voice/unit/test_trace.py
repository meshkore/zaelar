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


# ── active() — el trace para lectores que NO pueden heredar el ContextVar (2026-08-16) ────────────────────────────
# Auditoría de fuente real: los handlers de `voice/engine/pipeline/agent.py` (estado, VAD, métricas TTS/STT, el
# transcript de zaelar) corren en tareas HERMANAS de la que fija el trace del turno — nunca lo ven por el
# ContextVar, sea cual sea el orden temporal real (confirmado contra livekit-agents 1.6.6). `active()` es el
# puntero explícito que arregla justo eso.
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
    trace.adopt("")   # el ContextVar se limpia (fin del turno de kickoff)…
    assert trace.current() == ""
    assert trace.active() == tid, "…pero active() sigue apuntando al kickoff mientras no haya nada más reciente"


def test_active_expires_and_falls_back_to_general_not_a_stale_turn():
    """Un evento que llega mucho después de que el último trace se fijara no puede colgarse de un turno que
    probablemente ya cerró — reabriría en el master un flujo "cerrado" con actividad fantasma."""
    kickoff = trace.begin("motor arrancado", origin="kickoff")
    tid = trace.begin("hola", origin="turno")
    assert trace.active() == tid
    trace._active_at -= 10   # simula que pasaron 10s desde ese begin(), sin dormir de verdad
    assert trace.active() == kickoff
    assert trace.active(max_age_s=60) == tid, "el margen es configurable — con uno más ancho sigue siendo válido"


def test_cluster_and_pulso_origins_never_touch_active():
    """El puente MeshKore (connectors/meshkore/bridge.py) corre en el MISMO proceso y también llama begin() — si
    tocara active(), un tick de cluster le colgaría sus eventos al pipeline de VOZ (VAD/TTS/estado) del trace de
    una conversación de cluster que no tiene nada que ver."""
    tid = trace.begin("hola", origin="turno")
    trace.begin("[cluster:x] evento", origin="cluster")
    trace.begin("[cluster:x] heartbeat", origin="pulso")
    assert trace.active() == tid
    trace.adopt("")
