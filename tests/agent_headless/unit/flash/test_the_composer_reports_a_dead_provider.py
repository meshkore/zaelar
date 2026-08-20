"""V2-225 — el compositor LEÍA la cadena de proveedores y nunca la ESCRIBÍA.

`research._spec()` va por `provider_chain.pick()` y su docstring promete que «si el proveedor principal está sin
cuota, releva en vez de morir». La promesa no se cumplía, y no porque faltara el relevo: `note_failure()` tenía UN
solo llamador de producción en todo el árbol —`connectors/meshkore/brain.py`, el cerebro de cluster—, así que el
cooldown que dispara el relevo solo existía si el CLUSTER había fallado antes por el mismo sitio. El compositor
vivía de esa casualidad.

Medido por el arnés en dos rondas de `hotel-under-15-days` (2026-08-20): a las 20:01, 20:07 y 20:10 se eligió el
MISMO proveedor agotado las tres veces, con dos reintentos de FastClient cada una, y el worker salió a ciegas
después de cada una —

    research: el compositor falló (429 — [1310][Weekly/Monthly Limit Exhausted. Your limit will reset at
    2026-08-25 01:39:02]) — el worker sale SIN brief (búsqueda sin dirigir)

Ese texto es exactamente la forma que `classify_failure` lee como `exhausted` CON fecha de reset, que es el caso
que pone cooldown y devuelve relevo. No faltaba mecanismo: faltaba la llamada. Hasta el 2026-08-25 eso significaba
que TODA escalada de investigación salía sin dirigir — por eso el mejor «resultado» de una ronda fue un
espectáculo de flamenco de 25 €.
"""
import asyncio

import pytest

from nucleo import research

EXHAUSTED = "429 — [1310][Weekly/Monthly Limit Exhausted. Your limit will reset at 2027-01-01 01:39:02]"
LEAD = {"name": "zai", "base_url": "https://api.z.ai/v1", "model": "glm", "api_key": "k"}
RELAY = {"name": "deepseek", "base_url": "https://api.deepseek.com", "model": "v4", "api_key": "k"}


class _Spy:
    def __init__(self, relay=RELAY):
        self.relay, self.reported, self.used = relay, [], []

    def note_failure(self, text, tier=None, **kw):
        self.reported.append((text, tier))
        return self.relay


@pytest.fixture
def wired(monkeypatch):
    """La cadena y el cliente, mockeados; lo que se verifica es el contrato entre los dos.

    `ZAELAR_RESEARCH` se fija a mano porque el entorno de esta máquina lo trae a `0`, y con el compositor apagado
    `compose()` sale por la primera línea sin tocar nada: los siete tests pasarían por el camino equivocado."""
    monkeypatch.setenv("ZAELAR_RESEARCH", "1")
    spy = _Spy()
    from nucleo.flash import provider_chain as pc
    monkeypatch.setattr(pc, "pick", lambda *a, **k: LEAD)
    monkeypatch.setattr(pc, "spec_for", lambda t: t)
    monkeypatch.setattr(pc, "note_failure", spy.note_failure)

    class _Client:
        async def complete(self, msgs, spec=None, **kw):
            spy.used.append((spec or {}).get("name"))
            if (spec or {}).get("name") == LEAD["name"]:
                raise RuntimeError(EXHAUSTED)
            return '{"research": false}'

    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", lambda *a, **k: _Client())
    return spy


def test_the_dead_provider_is_REPORTED_to_the_chain(wired):
    asyncio.run(research.compose("búscame un hotel de 4 estrellas en Sevilla"))
    assert wired.reported, "nadie le dijo a la cadena que ese escalón está agotado: el relevo no puede dispararse"
    assert wired.reported[0][1] == LEAD


def test_and_the_message_that_travels_is_the_one_the_chain_knows_how_to_read(wired):
    """`classify_failure` distingue un 429 pelado (se reintenta solo) de uno de cuota agotada CON fecha de reset
    (releva y pone cooldown hasta el reset). Mandar otra cosa es no reportar."""
    asyncio.run(research.compose("hotel en Sevilla"))
    assert "Limit Exhausted" in wired.reported[0][0]


def test_THIS_task_is_saved_too_not_only_the_next_one(wired):
    """La evidencia son tres tareas seguidas a ciegas. Marcar el escalón arregla la siguiente; reintentar con el
    relevo arregla también la que está en curso."""
    asyncio.run(research.compose("hotel en Sevilla"))
    assert wired.used == [LEAD["name"], RELAY["name"]]


def test_with_NO_relay_the_fail_open_is_untouched(monkeypatch, wired):
    """El fail-open es correcto y no se toca: sin relevo, el worker sale sin brief, como siempre. Lo único que se
    añadió es la línea que marca el proveedor antes de rendirse."""
    wired.relay = None
    with pytest.raises(research.ComposerUnavailable):
        asyncio.run(research.compose("hotel en Sevilla"))
    assert wired.reported


def test_a_relay_that_is_the_SAME_tier_is_not_a_relay(monkeypatch, wired):
    """Sensitivity, y el bucle que este módulo existe para cortar: reintentar contra el escalón que acaba de
    fallar es gastar el presupuesto dos veces para el mismo 429."""
    wired.relay = LEAD
    with pytest.raises(research.ComposerUnavailable):
        asyncio.run(research.compose("hotel en Sevilla"))
    assert wired.used == [LEAD["name"]]


def test_a_model_PINNED_by_the_operator_is_never_reported(monkeypatch, wired):
    """`config §research.model` no es una elección de la cadena. Poner en cooldown un escalón que el compositor no
    usó relevaría al cerebro de cluster por culpa ajena."""
    monkeypatch.setattr("config.v2.get", lambda k, *a: ({"model": "mio", "base_url": "http://x"} if k == "research"
                                                        else {}), raising=False)
    with pytest.raises(research.ComposerUnavailable):
        asyncio.run(research.compose("hotel en Sevilla"))
    assert wired.reported == []


def test_a_timeout_is_not_a_dead_provider(wired, monkeypatch):
    """Sensitivity en la otra dirección: un compositor lento no es un proveedor sin cuota, y ponerlo en cooldown
    apagaría un escalón sano. El `except TimeoutError` sigue por delante y no pasa por aquí."""
    async def _slow(*a, **k):
        raise asyncio.TimeoutError()
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient",
                        lambda *a, **k: type("C", (), {"complete": staticmethod(_slow)})())
    with pytest.raises(research.ComposerUnavailable):
        asyncio.run(research.compose("hotel en Sevilla"))
    assert wired.reported == []
