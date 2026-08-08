"""Muro de login del navegador en la NUBE — cierre en limpio en vez de bucle infinito (2026-08-03).

Incidente real: el operador pidió una búsqueda en Wallapop desde el deploy en la nube (contenedor headless, sin
display); el sitio pidió login y todo se quedó embuclado para siempre — voz Y widget colgados, sin fallo ni aviso.
Causa: `_authenticate` siempre intentaba abrir una ventana VISIBLE para que el operador tecleara sus credenciales;
en un contenedor eso degrada a headless EN SILENCIO (`_ensure_page`) y la tarea se queda esperando un login que
nunca puede llegar. `_in_container()` corta esto ANTES de intentarlo, con un mensaje claro (instala la versión
local) en vez de un intento fantasma."""
import asyncio

import pytest

from widgets.navegador import owner, tasks


@pytest.fixture(autouse=True)
def _clean_state():
    owner._auth_resume.clear()
    yield
    owner._auth_resume.clear()


def _no_op_async(*_a, **_kw):
    async def _f(*a, **kw):
        return False
    return _f()


def test_container_bails_out_instead_of_opening_a_visible_window(monkeypatch):
    monkeypatch.setattr(owner, "_in_container", lambda: True)
    monkeypatch.setattr(owner, "_already_authenticated", lambda site: _no_op_async())

    tid = tasks.create("buscar motos en wallapop", title="Wallapop")
    asyncio.run(owner._authenticate(tid, "wallapop.com", site="wallapop.com", goal="buscar motos"))

    t = tasks.get(tid)
    assert t["status"] == "failed"                 # no se queda en needs_input esperando para siempre
    assert not t["awaiting_login"]
    last_event = (t["events"][-1] or {}).get("text", "") if t["events"] else ""
    assert "nube" in last_event


def test_other_paused_tasks_are_also_failed_not_left_hanging(monkeypatch):
    """`_begin_login` pausa OTRAS tareas activas mientras se resuelve el login (needs_input) — si el login no
    puede resolverse en la nube, esas tareas pausadas deben cerrarse también, no quedar colgadas para siempre."""
    monkeypatch.setattr(owner, "_in_container", lambda: True)
    monkeypatch.setattr(owner, "_already_authenticated", lambda site: _no_op_async())

    primary = tasks.create("buscar motos en wallapop", title="Wallapop")
    other = tasks.create("buscar coches en wallapop", title="Wallapop coches")
    owner._auth_resume[other] = {"goal": "buscar coches", "plan": "", "site": "wallapop.com"}
    tasks.set_status(other, "needs_input")

    asyncio.run(owner._authenticate(primary, "wallapop.com", site="wallapop.com", goal="buscar motos"))

    assert tasks.get(primary)["status"] == "failed"
    assert tasks.get(other)["status"] == "failed"
    assert owner._auth_resume == {}                 # drenado, nada queda esperando


def test_locally_the_visible_login_flow_is_not_short_circuited(monkeypatch):
    """Fuera de un contenedor, `_in_container()` no debe interceptar nada — la guarda es SOLO para cloud."""
    monkeypatch.setattr(owner, "_in_container", lambda: False)
    assert owner._in_container() is False
