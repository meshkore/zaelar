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


# ── ruido de fondo NUNCA fabrica una sesión por sí solo (2026-08-15) ────────────────────────────────────────
# Hallazgo real probando en vivo el ⏻ (V2-092): `identity.end_session()` cierra la sesión (`_session["id"]` a
# None) y acto seguido emite SU PROPIO evento "end" — categoría `system`. Con `session_id()` (que SE ABRE sola)
# como fuente del `sid`, ese mismo evento de cierre reabría una sesión NUEVA en el acto de cerrar la anterior —
# el master seguía viendo "EN CURSO" un segundo después de terminar. Lo mismo le pasaba a cualquier evento
# `run` del ⏻ (stop/start/pausing/resumed) disparado con el agente ya parado. La sesión debe quedarse CERRADA
# hasta que actividad REAL (no plomería) la vuelva a abrir.
def test_system_noise_does_not_resurrect_a_closed_session(monkeypatch):
    from observability import identity

    monkeypatch.setattr(identity, "_session", {"id": None, "started_ms": None, "source": ""})
    ev = {"kind": "run", "cat": "system"}
    observer.stamp_identity(ev)
    assert ev["sid"] == "", "un evento de plomería no puede reabrir lo que se acaba de cerrar"
    assert identity._session["id"] is None, "y desde luego no debe dejar una sesión nueva puesta en su lugar"


def test_real_activity_still_opens_a_session_that_was_closed(monkeypatch):
    """El contraste: el ruido de fondo no abre nada, pero actividad REAL sigue abriendo sola una sesión nueva
    tras un cierre — la garantía original ("un evento nunca queda sin sesión") sigue viva para lo que importa."""
    from observability import identity

    monkeypatch.setattr(identity, "_session", {"id": None, "started_ms": None, "source": ""})
    ev = {"kind": "brain", "cat": "flash"}
    observer.stamp_identity(ev)
    assert ev["sid"], "actividad real SÍ tiene que abrir una sesión si no había ninguna"
    assert identity._session["id"] == ev["sid"]
