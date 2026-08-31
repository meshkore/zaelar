"""Tests for nucleo/flash/escalate.py (V2-004 · T64) — escalation stub: registration + bus event."""
import pytest

import bus
from nucleo.flash import escalate


@pytest.fixture(autouse=True)
def _reset():
    escalate.reset()
    yield
    escalate.reset()


def test_escalate_registers_and_emits_bus():
    seen = []
    sink = lambda rec: seen.append(rec) if rec["topic"] == "escalate.requested" else None
    bus.add_sink(sink)
    try:
        tid = escalate.escalate_to_slowbrain("recuerda que mi coche está en el taller", context={"src": "voice"})
    finally:
        bus.remove_sink(sink)
    assert isinstance(tid, int) and tid > 0
    assert len(seen) == 1
    assert seen[0]["payload"]["id"] == tid
    assert "coche" in seen[0]["payload"]["request"]
    assert seen[0]["payload"]["context"] == {"src": "voice"}


def test_pending_and_summary_line():
    tid = escalate.escalate_to_slowbrain("arregla el bug del login")
    assert any(t["id"] == tid for t in escalate.pending())
    assert "TAREAS DE FONDO" in escalate.summary_line()
    escalate.finish(tid, "hecho")
    assert escalate.pending() == []
    assert escalate.summary_line() == ""


def test_finish_emits_done():
    seen = []
    sink = lambda rec: seen.append(rec["topic"]) if rec["topic"] == "escalate.done" else None
    tid = escalate.escalate_to_slowbrain("x")
    bus.add_sink(sink)
    try:
        escalate.finish(tid, "ok")
    finally:
        bus.remove_sink(sink)
    assert seen == ["escalate.done"]


def test_registry_bounded():
    for i in range(30):
        escalate.escalate_to_slowbrain(f"tarea {i}")
    assert len(escalate.pending()) <= 12
