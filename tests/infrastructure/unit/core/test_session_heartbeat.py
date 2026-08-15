"""
LATIDO de sesión hacia el control-plane (2026-08-15, propuesta del operador tras revisar la liveness de una
cuenta cloud): `identity.end_session()` es best-effort — si la Machine muere de golpe nunca llega — y el
backoffice tenía que ADIVINAR "¿sigue viva esta cuenta?" por la marca de tiempo del evento más reciente en el
SQLite de la propia cuenta (ruidosa: homeostasis/cron cuentan igual que actividad real). En vez de un canal
nuevo, `begin_session()` repite el mismo aviso de "start" que ya toca `last_seen_at` en el control-plane
(`userSessions.touch`, idempotente) cada `_HEARTBEAT_INTERVAL_S` mientras la sesión siga abierta, y `end_session()`
lo cancela. Estos tests cubren el ciclo de vida de esa tarea, no el transporte HTTP (`_report_to_control_plane`
ya tiene su propio guard no-op, probado aparte).
"""
from __future__ import annotations

import asyncio

import pytest

from observability import identity


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(identity, "_session", {"id": None, "started_ms": None, "source": ""})
    monkeypatch.setattr(identity, "_emit_session", lambda *a, **k: None)
    monkeypatch.setattr(identity, "_heartbeat", {"task": None})
    yield
    identity._stop_heartbeat()


def test_begin_session_starts_a_heartbeat_task_when_a_loop_is_running(monkeypatch):
    monkeypatch.setattr(identity, "_report_to_control_plane", lambda *a, **k: None)

    async def run():
        identity.begin_session(source="test", force=True)
        assert identity._heartbeat["task"] is not None
        assert isinstance(identity._heartbeat["task"], asyncio.Task)
        assert not identity._heartbeat["task"].done()

    asyncio.run(run())


def test_end_session_cancels_the_heartbeat_task(monkeypatch):
    monkeypatch.setattr(identity, "_report_to_control_plane", lambda *a, **k: None)

    async def run():
        identity.begin_session(source="test", force=True)
        task = identity._heartbeat["task"]
        identity.end_session("test")
        assert identity._heartbeat["task"] is None
        await asyncio.sleep(0)               # deja correr un tick para que la cancelación se propague
        assert task.cancelled() or task.done()

    asyncio.run(run())


def test_begin_session_without_a_running_loop_does_not_crash():
    """Fuera de un loop (arranque, un test síncrono) no hay a quién lanzarle una tarea — no debe reventar, y
    sencillamente no hay heartbeat que mantener."""
    info = identity.begin_session(source="test", force=True)
    assert info.get("id")
    assert identity._heartbeat["task"] is None


def test_the_heartbeat_loop_repeats_the_start_report_while_the_session_stays_open(monkeypatch):
    calls = []
    monkeypatch.setattr(identity, "_report_to_control_plane", lambda label, info: calls.append(label))
    monkeypatch.setattr(identity, "_HEARTBEAT_INTERVAL_S", 0.01)

    async def run():
        identity.begin_session(source="test", force=True)
        await asyncio.sleep(0.05)            # varios intervalos de sobra
        identity.end_session("test")

    asyncio.run(run())
    assert calls.count("start") >= 2, f"esperaba varios latidos, solo hubo {calls}"


def test_a_second_begin_session_does_not_leak_a_previous_heartbeat_task(monkeypatch):
    """`begin_session(force=True)` puede llamarse dos veces sin pasar por `end_session` (p.ej. un reset). La
    tarea anterior no puede quedar viva por detrás, latiendo por una sesión que ya no existe."""
    monkeypatch.setattr(identity, "_report_to_control_plane", lambda *a, **k: None)

    async def run():
        identity.begin_session(source="test", force=True)
        first = identity._heartbeat["task"]
        identity.begin_session(source="test", force=True)
        second = identity._heartbeat["task"]
        assert second is not first
        await asyncio.sleep(0)
        assert first.cancelled() or first.done()

    asyncio.run(run())
