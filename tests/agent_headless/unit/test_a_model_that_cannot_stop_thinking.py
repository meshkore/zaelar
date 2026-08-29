"""V2-488 — un modelo que NO PUEDE apagar el razonamiento tumbaba TODAS las búsquedas dirigidas, en silencio.

Medido en el plató US el 2026-08-29, idéntico en las dos rondas del hotel (20:03:02 y 20:40:36):

    research: el compositor falló (Error code: 400 - {'error': {'code': '1210', 'message': 'This model always
    engages in thinking and cannot be disabled; please use low, high, or max'}})
    — el worker sale SIN brief (búsqueda sin dirigir)

Y **no relevaba**: un 400 de parámetro no es una caída de proveedor, así que `classify_failure` no devuelve
tier de relevo y la excepción viaja hasta el fail-open. El motor degradaba a búsqueda ciega —lo que este
módulo existe para cerrar— cada vez que la cadena elegía un razonador puro, y por una línea NUESTRA.

La corrección tiene dos mitades y las dos se fijan aquí: reintentar **con** razonamiento, y con el
presupuesto que la deliberación necesita (1.600 vuelve truncado; el propio comentario del módulo ya había
medido 2.517 tokens de salida con thinking puesto).
"""
import asyncio

import pytest

from nucleo import research


RECHAZO = ("Error code: 400 - {'error': {'code': '1210', 'message': 'This model always engages in thinking "
           "and cannot be disabled; please use low, high, or max'}}")


# ── el predicado: distingue «no admite lo que le pido» de «se ha caído» ─────────────────────────────────────

@pytest.mark.parametrize("texto", [
    RECHAZO,
    "This model always engages in thinking and cannot be disabled",
    "reasoning cannot be disabled for this model",
])
def test_reconoce_el_rechazo(texto):
    assert research._no_puede_dejar_de_pensar(Exception(texto))


@pytest.mark.parametrize("texto", [
    "429 — [1310][Weekly/Monthly Limit Exhausted. Your limit will reset at 2026-08-25 01:39:02]",
    "Error code: 400 - invalid max_tokens",
    "Connection refused",
    "",
])
def test_NO_se_come_otros_fallos(texto):
    """Si esto tragara un 429 de cuota agotada, el relevo dejaría de dispararse — que es exactamente el
    defecto que V2-225 cerró. La cuarentena del proveedor tiene que seguir ocurriendo cuando toca."""
    assert not research._no_puede_dejar_de_pensar(Exception(texto))


# ── la conducta: el brief SALE, no se degrada a búsqueda ciega ──────────────────────────────────────────────

class _ClienteFalso:
    """Rechaza `no_thinking` como el proveedor real y anota con qué se le llamó cada vez."""

    llamadas: list = []

    def __init__(self):
        pass

    async def complete(self, msgs, *, spec=None, max_tokens=None, no_thinking=False, **kw):
        _ClienteFalso.llamadas.append({"max_tokens": max_tokens, "no_thinking": no_thinking})
        if no_thinking:
            raise RuntimeError(RECHAZO)
        return ('{"research": true, "goal": "mejor hotel en Nueva Orleans bajo 150$/noche", '
                '"domain": "hoteles", "breadth": {"min_candidates": 12}, "deliverable": {"n_final": 3}}')


@pytest.fixture
def _compositor(monkeypatch):
    _ClienteFalso.llamadas = []
    import nucleo.flash.fast_client as fc
    monkeypatch.setattr(fc, "FastClient", _ClienteFalso)
    monkeypatch.setattr(research, "enabled", lambda: True)
    monkeypatch.setattr(research, "_spec", lambda: (object(), "deepseek-directo"))
    return _ClienteFalso


def test_el_brief_SALE_aunque_el_modelo_no_pueda_dejar_de_pensar(_compositor):
    out = asyncio.run(research.compose("búscame el mejor hotel de Nueva Orleans bajo 150$ la noche"))
    assert out, "el compositor se rindió: el worker vuelve a salir a buscar a ciegas"
    assert len(_compositor.llamadas) == 2, "no se reintentó, o se reintentó de más"


def test_el_reintento_lleva_PRESUPUESTO_para_la_deliberacion(_compositor):
    """Con thinking puesto, el bloque se carga contra `max_tokens`: reintentar con los mismos 1.600 devuelve un
    brief truncado e ilegible — la trampa ya medida del razonador que se come el presupuesto."""
    asyncio.run(research.compose("búscame el mejor hotel de Nueva Orleans"))
    primera, segunda = _compositor.llamadas
    assert primera["no_thinking"] is True and primera["max_tokens"] == 1600
    assert segunda["no_thinking"] is False, "se vuelve a pedir lo mismo que el modelo acaba de rechazar"
    assert segunda["max_tokens"] > primera["max_tokens"], (
        "el reintento razona con el presupuesto del que no razonaba: vuelve truncado")


def test_el_tier_NO_se_pone_en_cuarentena_por_culpa_nuestra(_compositor, monkeypatch):
    """El proveedor no ha fallado: le hemos pedido algo que no admite. Marcarlo como caído lo aparta de la
    cadena para todo el mundo por un error de nuestro lado."""
    marcados = []
    monkeypatch.setattr(research, "_note_provider_failure",
                        lambda exc, tier: marcados.append(tier) or None)
    asyncio.run(research.compose("búscame el mejor hotel de Nueva Orleans"))
    assert marcados == [], f"se puso en cuarentena {marcados} por un 400 de parámetro nuestro"
