"""V2-488 — a model that CANNOT turn off reasoning was silently breaking ALL directed searches.

Measured on the US stage on 2026-08-29, identically in both hotel runs (20:03:02 and 20:40:36):

    research: the composer failed (Error code: 400 - {'error': {'code': '1210', 'message': 'This model always
    engages in thinking and cannot be disabled; please use low, high, or max'}})
    — the worker exits WITHOUT a brief (undirected search)

And it **did not fail over**: a parameter 400 is not a provider outage, so `classify_failure` does not return a
failover tier and the exception travels up to fail-open. The engine degraded to blind search —what this module
exists to prevent— whenever the chain selected a pure reasoner, because of one line of OUR code.

The fix has two halves, and both are enforced here: retry **with** reasoning, and with the
budget that deliberation requires (1,600 comes back truncated; the module's own comment had already
measured 2,517 output tokens with thinking enabled).
"""
import asyncio

import pytest

from nucleo import research


RECHAZO = ("Error code: 400 - {'error': {'code': '1210', 'message': 'This model always engages in thinking "
           "and cannot be disabled; please use low, high, or max'}}")


# ── the predicate: distinguishes “does not support what I request” from “has gone down” ────────────────────

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
    """If this swallowed a 429 for an exhausted quota, failover would stop triggering — exactly the
    defect that V2-225 fixed. Provider quarantine must continue to occur when appropriate."""
    assert not research._no_puede_dejar_de_pensar(Exception(texto))


# ── the behavior: the brief GETS OUT; it does not degrade to blind search ───────────────────────────────────

class _ClienteFalso:
    """Rejects `no_thinking` like the real provider and records how it was called each time."""

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
    """With thinking enabled, the block counts against `max_tokens`: retrying with the same 1,600 returns a
    truncated, unreadable brief — the already-measured trap of the reasoner consuming the budget."""
    asyncio.run(research.compose("búscame el mejor hotel de Nueva Orleans"))
    primera, segunda = _compositor.llamadas
    assert primera["no_thinking"] is True and primera["max_tokens"] == 1600
    assert segunda["no_thinking"] is False, "se vuelve a pedir lo mismo que el modelo acaba de rechazar"
    assert segunda["max_tokens"] > primera["max_tokens"], (
        "el reintento razona con el presupuesto del que no razonaba: vuelve truncado")


def test_el_tier_NO_se_pone_en_cuarentena_por_culpa_nuestra(_compositor, monkeypatch):
    """The provider has not failed: we asked it for something it does not support. Marking it as down removes it
    from the chain for everyone because of an error on our side."""
    marcados = []
    monkeypatch.setattr(research, "_note_provider_failure",
                        lambda exc, tier: marcados.append(tier) or None)
    asyncio.run(research.compose("búscame el mejor hotel de Nueva Orleans"))
    assert marcados == [], f"se puso en cuarentena {marcados} por un 400 de parámetro nuestro"
