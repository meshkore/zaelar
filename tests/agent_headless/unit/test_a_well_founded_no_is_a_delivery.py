"""Buscar bien y encontrar que NO existe es un resultado completo, y el prompt no lo decía.

Medido en `find-concert-tickets__es` (2026-08-28, plató 24/7, cerebro `deepseek-v4-flash`). No había concierto
de Rosalía en Madrid ese mes — una respuesta **completa y correcta**— y el worker llenó la hoja de eventos que
no eran, dejando a la persona **siete minutos** esperando. El juez: *«no cierra el resultado negativo como
conclusión principal y en su lugar llena la hoja con eventos irrelevantes»*.

El método ya cubría «no puedo certificarlo» (paso 7). Esto es **lo contrario** y faltaba: sí lo certifiqué, y
lo que certifiqué es que no existe. Sin decirlo, el único final que le queda al worker es seguir buscando —
volver con las manos vacías no está en su repertorio, así que rellena.
"""
from __future__ import annotations

from nucleo import dispatch_prompts as DP


def _metodo() -> str:
    return DP._method_block("/x/.venv/bin/python") if hasattr(DP, "_method_block") else _buscar_metodo()


def _buscar_metodo() -> str:
    """El bloque del método, sea cual sea la función que lo compone hoy."""
    import inspect
    src = inspect.getsource(DP)
    i = src.index("7) VERIFICA antes de cerrar")
    return src[i - 4000: i + 4000]


def test_el_no_se_declara_una_ENTREGA():
    t = _buscar_metodo()
    assert "SI LA RESPUESTA ES QUE NO HAY, ESO ES LA ENTREGA" in t


def test_y_se_dice_QUE_hay_que_contar_con_el():
    """Un «no» sin decir dónde miraste no es verificable, y quien lo lee no puede distinguirlo de no haberlo
    intentado — que es exactamente la duda que este producto tiene que quitar."""
    t = _buscar_metodo()
    i = t.index("ESO ES LA ENTREGA")
    assert "dónde miraste" in t[i:i + 400] and "descartaste" in t[i:i + 400]


def test_y_se_PROHÍBE_rellenar():
    """Es la mitad que evita que la regla se lea como «di que no y ya»: lo que se prohíbe es lo que hizo."""
    t = _buscar_metodo()
    i = t.index("ESO ES LA ENTREGA")
    assert "rellenar con lo que no cumple" in t[i:i + 500]


def test_no_pisa_el_paso_7():
    """«No puedo certificarlo» y «he certificado que no existe» son distintos y los dos tienen que estar: el
    primero es una limitación, el segundo es una respuesta."""
    t = _buscar_metodo()
    assert "si no se puede certificar, dilo con honestidad" in t
    assert t.index("si no se puede certificar") < t.index("ESO ES LA ENTREGA")
