"""V2-390 — desde fuera, todas las data-ops del cerebro se veían iguales.

La ruta de la UI (el operador toca un botón) YA emitía `widget/action` con el nombre de la acción dentro. La
del CEREBRO no: solo salía el `widget/data` anónimo que dispara `store.save`, así que un `add_to_playlist` y
un `set_volume` eran el mismo evento.

Medido en `play-music-and-build-playlist` (2026-08-27 13:29). Comprobado a mano contra el plató vivo, con la
ronda recién terminada:

    yt        → {"videoId": "0iLF_rtUbq0", "title": "Música relajante para trabajar…", "paused": false}
    playlists → [{"id": "curro", "name": "Curro", "tracks": []}]

O sea: la música SONABA y la lista «Curro» EXISTÍA. El veredicto fue **1/5, «alucinación de éxito»**, y su
razón textual: *«el mecanismo prueba (sin `create_playlist`, sin evidencias de audio) que ninguna de las dos
cosas ocurrió»*, citando «solo operaciones genéricas de datos». El instrumento acusando al producto, otra vez,
y con la nota más baja posible en dos dimensiones.

Dos mitades, porque una sola no arregla nada: el motor NOMBRA la op, y el arnés la LEE por su nombre.
"""
from __future__ import annotations

import asyncio

import pytest

from tests.use_cases.e2e.agent import verify as V


def _ev(label, wid, action=None, cat="widget"):
    e = {"cat": cat, "label": label, "id": wid}
    if action is not None:
        e["action"] = action
    return e


# ── el arnés lo LEE por su nombre ───────────────────────────────────────────────────────────────────────────

def test_una_op_con_nombre_se_cuenta_por_su_NOMBRE():
    ops = V.widget_ops([_ev("action", "musica", "add_to_playlist")])
    assert ops == {"musica": {"add_to_playlist": 1}}


def test_dos_ops_DISTINTAS_no_se_confunden():
    """El corazón: contarlas por la etiqueta daba `{action: 2}`, que es tanto como no decir nada."""
    ops = V.widget_ops([_ev("action", "musica", "add_to_playlist"),
                        _ev("action", "musica", "set_volume")])
    assert ops == {"musica": {"add_to_playlist": 1, "set_volume": 1}}


def test_una_op_que_FALLO_se_cuenta_APARTE():
    """Que el widget se negara y que el cambio entrara son hechos opuestos."""
    ops = V.widget_ops([_ev("action", "musica", "add_to_playlist"),
                        _ev("action_failed", "musica", "add_to_playlist")])
    assert ops == {"musica": {"add_to_playlist": 1, "add_to_playlist✗": 1}}


def test_una_op_SIN_nombre_lo_DICE():
    """Un hueco silencioso se rellena; hay que nombrarlo (V2-127/V2-133)."""
    assert V.widget_ops([_ev("action", "musica")]) == {"musica": {"(op sin nombre)": 1}}


def test_los_eventos_de_SIEMPRE_siguen_contandose_igual():
    """La otra dirección: `data`/`show`/`close` no pueden cambiar de forma, que es de lo que vive el resto
    del informe."""
    ops = V.widget_ops([_ev("data", "musica"), _ev("show", "youtube"), _ev("close", "youtube")])
    assert ops == {"musica": {"data": 1}, "youtube": {"show": 1, "close": 1}}


def test_la_instancia_se_sigue_colapsando_al_widget():
    assert V.widget_ops([_ev("action", "navegador::t2", "open")]) == {"navegador": {"open": 1}}


# ── el motor la NOMBRA ──────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def emisiones(monkeypatch):
    """Captura lo que el motor emite al ejecutar una data-op del cerebro."""
    vistos = []
    import voice.observer as _obs
    monkeypatch.setattr(_obs, "emit",
                        lambda kind, label, text="", role="", extra=None:
                        vistos.append({"kind": kind, "label": label, "text": text, **(extra or {})}))
    return vistos


def _corre(monkeypatch, resultado):
    import widgets.server_api as SA

    async def _disp(wid, action, payload):
        return resultado
    monkeypatch.setattr(SA, "_dispatch", _disp)
    return asyncio.run(SA.brain_action("musica", "add_to_playlist", {"playlist": "Curro"}))


def test_el_cerebro_NOMBRA_la_op_que_lanza(monkeypatch, emisiones):
    """El guarda que habría bastado: la ruta de la UI ya lo hacía y la del cerebro no."""
    _corre(monkeypatch, {"ok": True, "playlist": "curro"})
    con_nombre = [e for e in emisiones if e["label"] == "action"]
    assert len(con_nombre) == 1
    assert con_nombre[0]["action"] == "add_to_playlist" and con_nombre[0]["id"] == "musica"


def test_una_op_que_el_widget_RECHAZA_emite_su_propio_evento(monkeypatch, emisiones):
    """«No suena nada» es un hecho que el juez necesita; plegarlo en el evento de éxito es cómo sobrevive un
    «Hecho.» que no es verdad."""
    _corre(monkeypatch, {"ok": False, "error": "nothing_playing", "message": "No suena nada ahora."})
    fallos = [e for e in emisiones if e["label"] == "action_failed"]
    assert len(fallos) == 1
    assert fallos[0]["error"] == "nothing_playing" and fallos[0]["is_error"] is True
    assert "No suena nada" in fallos[0]["text"]


def test_una_op_que_SALE_BIEN_no_emite_fallo(monkeypatch, emisiones):
    """La bifurcación al otro lado: marcar fallo siempre haría el evento inútil."""
    _corre(monkeypatch, {"ok": True})
    assert not [e for e in emisiones if e["label"] == "action_failed"]


def test_el_is_error_viaja_DENTRO_de_extra():
    """`emit` no acepta `is_error` como kwarg y los extras se aplanan al evento. Con el kwarg suelto salta un
    TypeError que el `except` de alrededor se traga: el evento de fallo no se emitiría NUNCA. Cometido al
    escribir esto, y por eso el guarda existe."""
    import inspect

    import voice.observer as _obs
    assert "is_error" not in inspect.signature(_obs.emit).parameters
