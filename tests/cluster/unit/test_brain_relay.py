"""Relevo de proveedor DENTRO de un turno de cluster (`connectors/meshkore/brain.py`, 2026-08-03).

Antes: `make_brain()` fijaba el tier UNA VEZ al arrancar el server; con la cuota de Z.AI agotada, CADA turno
(el heartbeat insistiendo en responder a un peer) repetía la MISMA llamada rota → 429 en bucle, sin relevo, sin
aviso. Ahora `_brain()` consulta `provider_chain.pick()` en cada turno y, si el turno falla por el proveedor,
se releva y reintenta ESE MISMO turno una vez antes de rendirse.
"""
import asyncio

import pytest

from connectors.meshkore import brain
from nucleo.flash import provider_chain as pc

Z_AI = {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic", "model": "glm-5.2", "env": ["Z_AI_API_KEY"]}
AIMLAPI = {"name": "aimlapi", "base_url": "https://api.aimlapi.com/v1", "model": "", "env": ["AIMLAPI_KEY"]}
REAL_429_EXHAUSTED = ("429 Too Many Requests — {\"error\":{\"message\":"
                      "\"[1310][Weekly/Monthly Limit Exhausted. Your limit will reset at 2026-08-04 00:00:00]\"}}")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(pc, "_cooldown", {})
    monkeypatch.setattr(pc, "_loaded", True)
    monkeypatch.setattr(pc, "_save", lambda: None)
    yield


def test_a_provider_failure_relays_and_retries_the_same_turn(monkeypatch):
    """El turno con z.ai revienta con un 429 de cuota agotada → se releva a aimlapi y el MISMO turno se reintenta
    (el mensaje real-time al peer no se pierde solo porque el tier de cabecera esté sin cuota)."""
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [Z_AI, AIMLAPI])   # pick()/note_failure() se dejan REALES: el punto
    # del test es que, tras el fallo, la cadena real recalcule el relevo contra el cooldown que acaba de anotar.

    calls = []

    async def fake_respond(text, *, spec, **kw):
        calls.append(spec.base_url)
        if spec.base_url == Z_AI["base_url"]:
            raise RuntimeError(REAL_429_EXHAUSTED)
        return "hola desde el relevo"

    monkeypatch.setattr("nucleo.flash.cluster.respond", fake_respond)
    b = brain.make_brain()
    out = asyncio.run(b("hola"))

    assert out == "hola desde el relevo"
    assert calls == [Z_AI["base_url"], AIMLAPI["base_url"]]      # un intento, un relevo, un reintento — no más
    assert pc._cooldown.get("z.ai", 0) > 0                        # z.ai queda en cooldown (STICKY para el próximo turno)


def test_a_passing_rate_limit_is_not_relayed(monkeypatch):
    """Un 429 desnudo (sin texto de cuota) es rate-limit pasajero — no releva, se propaga (el bridge ya lo loguea
    y el heartbeat lo reintentará solo más tarde, no hay que quemar el proveedor por esto)."""
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [Z_AI])

    async def fake_respond(text, *, spec, **kw):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr("nucleo.flash.cluster.respond", fake_respond)
    b = brain.make_brain()
    with pytest.raises(RuntimeError):
        asyncio.run(b("hola"))
    assert pc._cooldown == {}                                     # no se penaliza un blip pasajero


def test_no_tier_available_raises_before_calling_the_engine(monkeypatch):
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [])
    monkeypatch.setattr(pc, "pick", lambda *a, **k: None)
    b = brain.make_brain()
    with pytest.raises(RuntimeError):
        asyncio.run(b("hola"))
