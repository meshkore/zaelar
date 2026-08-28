"""Cuando la hoja del encargo no se resuelve, el prompt se compone como si no hubiera nada.

Y esa es la avería medida en V2-432: de las **48** rondas cuya hoja llegó a tener filas con nombre, **45**
tuvieron turnos en los que el bloque vivo le dijo al modelo que la tarea seguía atascada — **257 turnos**. El
modelo contestó «sin novedades» y el juez lo puntuó por negar lo que tenía delante.

El fallo no hace ruido: `_sheet_of_tab` devuelve `""`, `_sheet_has_rows` devuelve `False`, la cara de
resultados no se enciende, y el resultado es indistinguible de que de verdad no haya nada. Sin una línea que
lo diga, la avería solo se puede inferir cruzando el instante en que la hoja se llenó con el texto de cada
prompt — que es lo que hubo que hacer para encontrarla.

Se emite en `_sheet_of_tab` y no en cada llamante porque los DOS caminos de resolución mueren ahí.
"""
from __future__ import annotations

import pytest

from nucleo.flash import errand_sheet as ES


@pytest.fixture
def _emitido(monkeypatch):
    vistos: list[dict] = []
    import voice.observer as OBS
    monkeypatch.setattr(OBS, "emit",
                        lambda kind, label, text="", role="", extra=None: vistos.append(
                            {"label": label, "extra": dict(extra or {})}))
    return vistos


def _sin_resolver(monkeypatch):
    """Ni sello en la pestaña ni registro de sesiones: la firma exacta de la avería."""
    import widgets.navegador.tasks as _t
    import nucleo.dispatch as _d
    monkeypatch.setattr(_t, "get", lambda *_a, **_k: {})
    monkeypatch.setattr(_d, "sheet_for_nav_task", lambda *_a, **_k: "")


def test_una_hoja_sin_resolver_lo_DICE(monkeypatch, _emitido):
    _sin_resolver(monkeypatch)
    assert ES._sheet_of_tab("6175ca-1") == ""
    assert _emitido and "SIN RESOLVER" in _emitido[0]["label"]
    assert _emitido[0]["extra"]["nav_task"] == "6175ca-1", "sin el id no se puede ir a mirar cuál era"


def test_una_hoja_que_SÍ_resuelve_no_dice_nada(monkeypatch, _emitido):
    """La mitad de sensibilidad: una línea que sale en cada composición del prompt es ruido puro, y el bloque
    vivo se compone en todos los turnos."""
    import widgets.navegador.tasks as _t
    monkeypatch.setattr(_t, "get", lambda *_a, **_k: {"sheet": "results::6175ca-1"})
    assert ES._sheet_of_tab("6175ca-1") == "results::6175ca-1"
    assert _emitido == []


def test_el_REGISTRO_como_respaldo_tampoco_avisa(monkeypatch, _emitido):
    """El segundo camino es tan válido como el primero: avisar ahí sería llamar avería a lo que funciona."""
    import widgets.navegador.tasks as _t
    import nucleo.dispatch as _d
    monkeypatch.setattr(_t, "get", lambda *_a, **_k: {})
    monkeypatch.setattr(_d, "sheet_for_nav_task", lambda *_a, **_k: "results::6175ca-1")
    assert ES._sheet_of_tab("6175ca-1") == "results::6175ca-1"
    assert _emitido == []


def test_instrumentar_NO_puede_tumbar_el_prompt(monkeypatch):
    """El bloque vivo se compone en cada turno: una excepción aquí dejaría al operador sin turno entero."""
    _sin_resolver(monkeypatch)
    import voice.observer as OBS
    monkeypatch.setattr(OBS, "emit", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert ES._sheet_of_tab("6175ca-1") == ""


def test_live_blocks_sigue_usando_LA_MISMA_funcion():
    """La extracción no puede haber dejado dos copias: es la deuda que este repo pagó cuatro veces en una
    semana, y aquí significaría que el aviso existe en un sitio y el prompt se compone con el otro."""
    from nucleo.flash import live_blocks as LB
    assert LB._sheet_of_tab is ES._sheet_of_tab


# ── Y la otra mitad: RESUELTA, pero no es la que tiene las filas ────────────────────────────────────────────
def test_una_hoja_resuelta_y_VACIA_tambien_lo_dice(monkeypatch, _emitido):
    """Fallar al resolver ya se contaba. Resolver a la caja EQUIVOCADA se veía exactamente igual que acertar —
    y era el caso de `search-buy-guitar__es` (2026-08-28): `unresolved_errand_sheets.n` salió a **0**, o sea
    que resolvió, y aun así hubo seis turnos en los que al modelo no se le dijo que tuviera nada, con quince
    candidatos en la hoja. Sin esta línea el diagnóstico se queda en «resolvió bien y algo pasa después»."""
    from nucleo.flash import live_blocks as LB
    import widgets.results.data as _rd
    monkeypatch.setattr(LB, "_sheet_of_tab", lambda *_a, **_k: "results")
    monkeypatch.setattr(_rd, "view_data", lambda *_a, **_k: {"items": []})
    assert LB._sheet_has_rows("6175ca-1") is False
    assert _emitido and "RESUELTA PERO VACÍA" in _emitido[0]["label"]
    assert _emitido[0]["extra"]["hoja"] == "results", "sin decir CUÁL caja miró no se puede comparar"


def test_una_hoja_resuelta_CON_filas_no_dice_nada(monkeypatch, _emitido):
    """La mitad de sensibilidad: es el camino sano y se recorre en cada turno."""
    from nucleo.flash import live_blocks as LB
    import widgets.results.data as _rd
    monkeypatch.setattr(LB, "_sheet_of_tab", lambda *_a, **_k: "results::6175ca-1")
    monkeypatch.setattr(_rd, "view_data", lambda *_a, **_k: {"items": [{"title": "Yamaha F370BL"}]})
    assert LB._sheet_has_rows("6175ca-1") is True
    assert _emitido == []


def test_una_lectura_que_REVIENTA_tampoco_se_calla(monkeypatch, _emitido):
    """El tercer camino mudo, y el que quedaba. Medido el 2026-08-28 en `weekend-motor-events__es`: cuatro
    turnos ciegos con las DOS señales anteriores a cero — ni falló al resolver ni encontró la caja vacía—, así
    que solo quedaba que la lectura reventara y el `except` se lo tragase.

    Un fallo que se traga a sí mismo es peor que uno ruidoso: deja al prompt diciendo que no hay nada y a
    quien investiga sin nada que leer.
    """
    from nucleo.flash import live_blocks as LB
    import widgets.results.data as _rd
    monkeypatch.setattr(LB, "_sheet_of_tab", lambda *_a, **_k: "results::6175ca-1")
    monkeypatch.setattr(_rd, "view_data", lambda *_a, **_k: (_ for _ in ()).throw(KeyError("items")))
    assert LB._sheet_has_rows("6175ca-1") is False
    assert _emitido and "ILEGIBLE" in _emitido[0]["label"]
    assert "KeyError" in _emitido[0]["extra"]["error"], "sin el error no hay nada que investigar"
