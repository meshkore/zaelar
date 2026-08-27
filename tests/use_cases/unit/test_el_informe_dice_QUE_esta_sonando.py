"""V2-392 — «suena algo de verdad» era incomprobable desde el informe.

`widget_ops` dice qué se TOCÓ. No es lo mismo que si algo acabó pasando, y en los casos de medios la
diferencia es el criterio entero: «SUENA ALGO DE VERDAD» es literalmente la primera mitad de
`play-music-and-build-playlist`.

Medido el 2026-08-27 a las 14:02, comprobado a mano contra el plató con la ronda recién terminada:

    yt        → {"videoId": "263Vb6xiifo", "title": "MUSICA ZEN ULTRA RELAJANTE…", "paused": false}
    playlists → [{"name": "Curro", "tracks": [{"title": "MUSICA ZEN ULTRA RELAJANTE…"}]}]

Sonaba, y la lista tenía DENTRO esa misma canción: las dos mitades del caso, cumplidas. Veredicto: **3/5**,
«el asistente miente al afirmar que reproduce música sin tener la confirmación técnica necesaria (evidencia
cero)». El producto lo había hecho y nada podía decirlo.

El motor YA lo sabía —`widgets/producers.py` evalúa `active_when` contra el `view_data()` del widget— y lo que
faltaba era poder PREGUNTÁRSELO desde fuera del proceso. Se pregunta, no se deduce: reimplementar `active_when`
en el arnés sería una segunda verdad, capaz de divergir justo de la que usa el producto.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from tests.use_cases.e2e.agent import probe_client as PC
from tests.use_cases.e2e.agent import verify as V


def _cuerpo(resp) -> dict:
    return json.loads(bytes(resp.body).decode("utf-8"))


# ── el motor contesta ───────────────────────────────────────────────────────────────────────────────────────

def test_el_endpoint_devuelve_lo_que_dice_el_MOTOR(monkeypatch):
    import widgets.producers as P
    import widgets.server_api as SA

    async def _producing(*, channel=None):
        return ["musica"]
    monkeypatch.setattr(P, "producing", _producing)
    assert _cuerpo(asyncio.run(SA.producing_endpoint())) == {"producing": ["musica"]}


def test_si_el_motor_no_sabe_responder_NO_revienta(monkeypatch):
    """Es un dato de diagnóstico: tumbar una lectura del informe costaría la ronda entera."""
    import widgets.producers as P
    import widgets.server_api as SA

    async def _boom(*, channel=None):
        raise RuntimeError("el registro no está listo")
    monkeypatch.setattr(P, "producing", _boom)
    cuerpo = _cuerpo(asyncio.run(SA.producing_endpoint()))
    assert cuerpo["producing"] == [] and "no está listo" in cuerpo["error"]


# ── el arnés lo lee ─────────────────────────────────────────────────────────────────────────────────────────

def test_el_cliente_lee_la_lista(monkeypatch):
    monkeypatch.setattr(PC, "_get", lambda path, timeout=15.0: {"producing": ["musica", "youtube"]})
    assert PC.widgets_producing() == ["musica", "youtube"]


def test_el_cliente_pregunta_a_la_RUTA_correcta(monkeypatch):
    visto = {}
    monkeypatch.setattr(PC, "_get", lambda path, timeout=15.0: visto.setdefault("path", path) and {})
    PC.widgets_producing()
    assert visto["path"] == "/widgets/producing"


def test_un_motor_mudo_da_lista_VACIA_y_no_lanza(monkeypatch):
    def _boom(path, timeout=15.0):
        raise OSError("conexión rechazada")
    monkeypatch.setattr(PC, "_get", _boom)
    assert PC.widgets_producing() == []


def test_una_respuesta_SIN_el_campo_no_inventa_nada(monkeypatch):
    monkeypatch.setattr(PC, "_get", lambda path, timeout=15.0: {"error": "404"})
    assert PC.widgets_producing() == []


# ── y llega al informe ──────────────────────────────────────────────────────────────────────────────────────

def test_el_informe_de_mecanismo_LLEVA_lo_que_suena(monkeypatch):
    """El guarda que habría bastado: el criterio pedía `yt.videoId` y el informe no traía nada de eso."""
    monkeypatch.setattr(V.probe_client, "widgets_producing", lambda: ["musica"])
    mech = V.mechanism_report([], [])
    assert mech["widgets_producing"] == ["musica"]


def test_el_arnes_NO_reimplementa_active_when():
    """Se PREGUNTA al motor. Una copia de `active_when` aquí es una segunda verdad que puede divergir de la que
    usa el producto — y la que decide qué se ve en pantalla es la del producto.

    ⚠️ Sobre el CÓDIGO, no sobre el comentario: la primera versión casaba la cadena a secas y salía ROJA porque
    el propio docstring de `widgets_producing` explica por qué NO se reimplementa. Un guarda que lee la
    explicación en vez del código es el mismo fallo que ya se pagó con `extract=None` en V2-380, del revés.
    """
    import ast
    for f in ("tests/use_cases/e2e/agent/verify.py", "tests/use_cases/e2e/agent/probe_client.py"):
        arbol = ast.parse(Path(f).read_text(encoding="utf-8"))
        # Un literal `"active_when"` en el arnés solo puede ser el principio de una copia de la regla; el
        # docstring que EXPLICA por qué no se copia es prosa y no cuenta (ast.Constant no ve un docstring
        # suelto de módulo/función como este literal, porque se compara por igualdad exacta).
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Constant) and nodo.value == "active_when":
                assert False, f"{f} nombra `active_when` como dato: se PREGUNTA al motor, no se copia"
