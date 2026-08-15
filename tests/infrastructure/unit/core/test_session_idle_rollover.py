"""
Techo de INACTIVIDAD REAL de la sesión de trabajo (2026-08-13, petición del operador: una sesión que se queda
parada/cerrada no puede seguir viva para siempre acumulando eventos de tramos de trabajo distintos).

`observability.identity.note_real_activity()` es la pieza nueva: cierra la sesión abierta si lleva más de
`IDLE_TIMEOUT_MS` sin actividad REAL, y `voice.observer.stamp_identity` la llama para todo evento que NO sea
ruido de fondo (`system`/`pulse`) antes de resolver `sid`. Estos tests controlan el reloj a mano (sin
`time.sleep`) y verifican las tres garantías: rota tras un hueco real, el ruido de fondo no lo dispara ni lo
extiende, y una reconexión normal (hueco corto) sigue sin partir la sesión en dos.
"""
from __future__ import annotations

import pytest

from observability import identity
from voice import observer


@pytest.fixture(autouse=True)
def _clean_identity_state(monkeypatch):
    """Cada test parte de una sesión abierta y un reloj propio — nunca del estado real del proceso."""
    monkeypatch.setattr(identity, "_session", {"id": "s0", "started_ms": 0, "source": "test"})
    monkeypatch.setattr(identity, "_last_real_activity_ms", {"v": 0})
    monkeypatch.setattr(identity, "IDLE_TIMEOUT_MS", 5 * 60_000)
    # `end_session`/`begin_session` emiten al observer y reportan al control-plane — ninguno de los dos debe
    # tocar red ni el bus real en un test unitario.
    monkeypatch.setattr(identity, "_emit_session", lambda *a, **k: None)
    monkeypatch.setattr(identity, "_report_to_control_plane", lambda *a, **k: None)

    clock = {"ms": 0}
    monkeypatch.setattr(identity.time, "time", lambda: clock["ms"] / 1000)
    return clock


def _stamp(cat: str, clock: dict, ms: int) -> dict:
    clock["ms"] = ms
    ev: dict = {"kind": "brain" if cat == "flash" else cat, "cat": cat}
    observer.stamp_identity(ev)
    return ev


def test_a_real_gap_past_the_timeout_rotates_the_session(_clean_identity_state):
    clock = _clean_identity_state
    first = _stamp("flash", clock, 0)
    later = _stamp("flash", clock, 6 * 60_000)  # 6 min > 5 min de techo
    assert first["sid"] == "s0"
    assert later["sid"] != "s0"
    assert later["sid"], "la rotación deja la sesión NUEVA ya abierta, no huérfana"


def test_background_noise_never_extends_nor_triggers_rotation(_clean_identity_state):
    clock = _clean_identity_state
    _stamp("flash", clock, 0)
    # Puro ruido de fondo durante 20 min — ninguno es actividad real.
    for minute in range(1, 21):
        pulse = _stamp("pulse" if minute % 2 else "system", clock, minute * 60_000)
        assert pulse["sid"] == "s0", "el ruido de fondo no puede disparar una rotación por sí solo"
    # Y tampoco tuvo que extender el reloj: la actividad real que llega después del mismo hueco largo SÍ rota.
    real = _stamp("worker", clock, 20 * 60_000 + 1)
    assert real["sid"] != "s0"


def test_reconnection_within_the_window_keeps_the_same_session(_clean_identity_state):
    clock = _clean_identity_state
    _stamp("flash", clock, 0)
    soon = _stamp("flash", clock, 2 * 60_000)  # 2 min < 5 min de techo
    assert soon["sid"] == "s0", "una reconexión por un bache no puede partir la sesión en dos"


# ── background noise NEVER fabricates a session by itself (2026-08-15) ─────────────────────────────────────
# Real finding while live-testing ⏻ (V2-092): `identity.end_session()` closes the session (`_session["id"]` to
# None) and right after emits ITS OWN "end" event — category `system`. With `session_id()` (which SELF-OPENS)
# as the source of `sid`, that same close event would reopen a NEW session in the act of closing the previous
# one — the master kept showing "EN CURSO" a second after finishing. The same happened with any ⏻ `run` event
# (stop/start/pausing/resumed) fired while the agent was already stopped. The session must stay CLOSED until
# REAL activity (not plumbing) reopens it.
def test_system_noise_does_not_resurrect_a_closed_session(monkeypatch):
    from observability import identity

    monkeypatch.setattr(identity, "_session", {"id": None, "started_ms": None, "source": ""})
    ev = {"kind": "run", "cat": "system"}
    observer.stamp_identity(ev)
    assert ev["sid"] == "", "a plumbing event can't reopen what just closed"
    assert identity._session["id"] is None, "and certainly must not leave a new session in its place"


def test_real_activity_still_opens_a_session_that_was_closed(monkeypatch):
    """The contrast: background noise opens nothing, but REAL activity still opens a new session on its own
    after a close — the original guarantee ("an event never goes without a session") is still alive where it
    matters."""
    from observability import identity

    monkeypatch.setattr(identity, "_session", {"id": None, "started_ms": None, "source": ""})
    ev = {"kind": "brain", "cat": "flash"}
    observer.stamp_identity(ev)
    assert ev["sid"], "real activity DOES have to open a session if none was open"
    assert identity._session["id"] == ev["sid"]
